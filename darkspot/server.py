"""Real-time server. POST /api/analyze streams NDJSON: {"stage","msg"} progress lines, then {"done": result} or {"error"}.
Zero dependencies, binds 127.0.0.1 by default. Run: python -m darkspot"""
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import analyze as A, checklist as C, net
from .facts import SCHEMAS

UI = Path(__file__).resolve().parent.parent / "ui"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
HITS, LOCK, MAX_BODY, PER_MIN, MAX_PDF = {}, threading.Lock(), 1_500_000, 12, 900_000

def limited(ip):
    with LOCK:
        now = time.time(); h = [x for x in HITS.get(ip, []) if now - x < 60] + [now]; HITS[ip] = h
        return len(h) > PER_MIN

def live(mode):
    if mode == "claude" and os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("DARKSPOT_MODEL"):
        from .llm import ClaudeExtractor
        return ClaudeExtractor()
    return None

def validate(b):
    """Stage 1: question and goal. Raises ValueError with a message that is safe to show."""
    q, tpl = str(b.get("question", ""))[:300], b.get("template", "auto")
    if tpl != "auto" and tpl not in SCHEMAS: raise ValueError("Unknown topic.")
    p = dict(q=q, tpl=tpl, mode=b.get("mode"), sample=bool(b.get("sample")), discover=bool(b.get("discover")), urls=[], texts=[], pdfs=[])
    if p["sample"]:
        p["tpl"] = "scholarship" if tpl == "auto" else tpl; p["q"] = q or "What should I verify before applying?"; return p
    p["urls"] = [str(u)[:500] for u in b.get("urls", []) if str(u).strip()]
    p["texts"] = [(str(t.get("name", ""))[:60], str(t.get("text", ""))[:200_000]) for t in b.get("texts", []) if str(t.get("text", "")).strip()]
    p["pdfs"] = [(str(f.get("name", ""))[:60], str(f.get("b64", ""))[:MAX_PDF]) for f in b.get("pdfs", []) if f.get("b64")][:3]
    if not q.strip(): raise ValueError("Enter a question.")
    n = len(p["urls"]) + len(p["texts"]) + len(p["pdfs"])
    if not n and not p["discover"]: raise ValueError("Add at least one link, PDF or pasted text, or turn on search discovery.")
    if n > A.MAX_SOURCES: raise ValueError(f"Use at most {A.MAX_SOURCES} sources.")
    return p

def run(p, emit):
    emit(1, "Question received" + (": " + p["q"] if p["q"] else ""))
    llm = live(p["mode"])
    if p["mode"] == "claude" and not llm: emit(1, "Live reader unavailable (needs anthropic package, key and model). Using offline rules.")
    slots, origin = C.build(p["q"], p["tpl"], llm)
    emit(2, f"Expected-answer checklist: {len(slots)} items from {origin}")
    if p["sample"]: srcs = A.load_sources(sample=True, emit=emit)
    else:
        urls = list(p["urls"])
        room = A.MAX_SOURCES - len(urls) - len(p["texts"]) - len(p["pdfs"])
        if p["discover"] and room > 0:
            try: found = net.discover(p["q"], min(3, room)); emit(3, f"Search discovery added {len(found)} pages"); urls += found
            except net.Blocked as e: emit(3, str(e))
        srcs = A.load_sources(urls, p["texts"], p["pdfs"], emit=emit)
    return A.analyze(p["q"], p["tpl"], srcs, llm, emit, slots, origin)

class H(BaseHTTPRequestHandler):
    server_version = "DarkSpot"
    def _hdrs(self, ctype, n=None):
        for k, v in (("Content-Type", ctype), ("Content-Security-Policy", CSP), ("X-Content-Type-Options", "nosniff"),
                     ("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store")) + ((("Content-Length", str(n)),) if n is not None else ()):
            self.send_header(k, v)
        self.end_headers()
    def _send(self, code, data, ctype="application/json; charset=utf-8"):
        b = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code); self._hdrs(ctype, len(b)); self.wfile.write(b)
    def _line(self, obj):
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode() + b"\n"); self.wfile.flush()
    def do_GET(self):
        if self.path in STATIC:
            f, ct = STATIC[self.path]; return self._send(200, (UI / f).read_bytes(), ct)
        self._send(404, {"error": "Not found."})
    def do_POST(self):
        if self.path != "/api/analyze": return self._send(404, {"error": "Not found."})
        if limited(self.client_address[0]): return self._send(429, {"error": "Too many requests. Wait a minute."})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_BODY: return self._send(413, {"error": "Request too large."})
            body = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(body, dict): raise TypeError
            p = validate(body)
        except ValueError as e:
            return self._send(400, {"error": str(e) if str(e).startswith(("Enter", "Add ", "Use at", "Unknown")) else "Bad request."})
        except TypeError: return self._send(400, {"error": "Bad request."})
        self.send_response(200); self._hdrs("application/x-ndjson; charset=utf-8")
        try:
            self._line({"stage": 1, "msg": "Started"})
            try: self._line({"done": run(p, lambda s, m: self._line({"stage": s, "msg": m}))})
            except (BrokenPipeError, ConnectionResetError): raise
            except Exception: self._line({"error": "Something went wrong. Try again."})
        except (BrokenPipeError, ConnectionResetError): pass
    def log_message(self, *a): pass

def main():
    host, port = os.environ.get("DARKSPOT_HOST", "127.0.0.1"), int(os.environ.get("DARKSPOT_PORT", "8000"))
    print(f"DarkSpot running at http://{host}:{port}"); ThreadingHTTPServer((host, port), H).serve_forever()
