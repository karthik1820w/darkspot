"""Zero-dependency web server. Binds to 127.0.0.1 by default. Run: python -m darkspot"""
import json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from . import analyze as A
from .facts import SCHEMAS

UI = Path(__file__).resolve().parent.parent / "ui"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
HITS, LOCK, MAX_BODY, PER_MIN = {}, threading.Lock(), 1_000_000, 12

def limited(ip):
    with LOCK:
        now = time.time(); h = [x for x in HITS.get(ip, []) if now - x < 60] + [now]; HITS[ip] = h
        return len(h) > PER_MIN

def extractor(mode):
    if mode == "claude" and os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("DARKSPOT_MODEL"):
        from .llm import ClaudeExtractor
        return ClaudeExtractor()
    return None

def run(body):
    q, tpl = str(body.get("question", ""))[:300], body.get("template", "scholarship")
    if tpl not in SCHEMAS: raise ValueError("Unknown template.")
    if body.get("sample"): return A.analyze(q or "What should I verify before applying?", tpl, A.load_sources(sample=True))
    urls = [str(u)[:500] for u in body.get("urls", []) if str(u).strip()]
    texts = [(str(t.get("name", ""))[:60], str(t.get("text", ""))[:200_000]) for t in body.get("texts", []) if str(t.get("text", "")).strip()]
    if not q.strip(): raise ValueError("Enter a question.")
    if not urls and not texts: raise ValueError("Add at least one link or pasted text.")
    if len(urls) + len(texts) > A.MAX_SOURCES: raise ValueError(f"Use at most {A.MAX_SOURCES} sources.")
    return A.analyze(q, tpl, A.load_sources(urls, texts), extractor(body.get("mode")))

class H(BaseHTTPRequestHandler):
    server_version = "DarkSpot"
    def _send(self, code, data, ctype="application/json; charset=utf-8"):
        b = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        for k, v in (("Content-Type", ctype), ("Content-Length", str(len(b))), ("Content-Security-Policy", CSP),
                     ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store")):
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
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
            result = run(json.loads(self.rfile.read(n) or b"{}"))
        except ValueError as e:
            return self._send(400, {"error": str(e) if "Enter" in str(e) or "Add " in str(e) or "Use at" in str(e) or "template" in str(e) else "Bad request."})
        except Exception:
            return self._send(500, {"error": "Something went wrong. Try again."})
        self._send(200, result)
    def log_message(self, *a): pass

def main():
    host, port = os.environ.get("DARKSPOT_HOST", "127.0.0.1"), int(os.environ.get("DARKSPOT_PORT", "8000"))
    print(f"DarkSpot running at http://{host}:{port}"); ThreadingHTTPServer((host, port), H).serve_forever()
