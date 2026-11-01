"""Transport-independent, STATELESS API. The same functions serve Vercel (api/*.py) and the local dev server.
Every request carries what it needs, because serverless instances share no memory.
  POST /api/checklist  question -> expected-answer checklist (+ optional search discovery)
  POST /api/sources    ONE source (url | text | pdf | sample) -> cleaned, dated, hashed, signed evidence
  POST /api/analyze    question + checklist + sources (+ previous snapshot) -> findings
Evidence integrity: if DARKSPOT_SECRET is set, sources are HMAC-signed and analyze rejects edited ones."""
import hashlib, hmac, json, os, re, threading, time
from datetime import date
from http.server import BaseHTTPRequestHandler
from . import analyze as A, checklist as C, net, text as T
from .facts import SCHEMAS

MAX_BODY, MAX_PDF, MAX_TEXT = 4_000_000, 900_000, 200_000
PER_MIN = int(os.environ.get("DARKSPOT_RATE", "60"))   # requests per minute per client; a run uses about 5
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
SIGNED = ("name", "url", "hash", "date", "date_method", "authority", "retrieved_at")
HITS, LOCK = {}, threading.Lock()

class ApiError(Exception):
    def __init__(self, msg, code=400): super().__init__(msg); self.code = code

def limited(ip):
    """Best effort only: serverless instances do not share this dict. Use Vercel's firewall rate limiting for a real limit."""
    with LOCK:
        now = time.time(); h = [x for x in HITS.get(ip, []) if now - x < 60] + [now]; HITS[ip] = h
        if len(HITS) > 5000: HITS.clear()
        return len(h) > PER_MIN

def live(mode):
    if mode == "claude" and os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("DARKSPOT_MODEL"):
        from .llm import ClaudeExtractor
        return ClaudeExtractor()
    return None

def sign(src):
    key = os.environ.get("DARKSPOT_SECRET", "").encode()
    if not key: return ""
    return hmac.new(key, json.dumps({k: src.get(k) for k in SIGNED}, sort_keys=True).encode(), hashlib.sha256).hexdigest()

def wire(s):
    """Source as sent to the browser (and echoed back to /api/analyze)."""
    out = {k: (str(s[k]) if k == "date" and s[k] else s.get(k)) for k in
           ("id", "name", "url", "text", "date", "date_method", "authority", "injection", "error", "truncated", "hash", "retrieved_at")}
    out["sig"] = "" if s["error"] else sign(out)
    return out

SAMPLE_AUTH = {u: a for _, u, _, a in A.SAMPLE_SET}     # the fictional sample pages carry their authority by design

def trusted_authority(url, claimed):
    """Authority is recomputed here, never taken from the client: a link is judged by its domain, pasted text and PDFs have fixed labels."""
    if url in SAMPLE_AUTH: return SAMPLE_AUTH[url]
    if url: return A.authority(url)
    return claimed if claimed in ("pasted", "uploaded") else "pasted"

def from_wire(w, i):
    """Rebuild a trusted source from client-supplied data. Derived fields are recomputed, hash and signature are checked."""
    if not isinstance(w, dict): raise ApiError("Bad source.")
    sid, name, url = f"S{i}", str(w.get("name", ""))[:60], (str(w["url"])[:500] if w.get("url") else None)
    if w.get("error"): return A.failed(i, name, url, str(w["error"])[:200])
    text = str(w.get("text", ""))[:MAX_TEXT]
    if hashlib.sha256(text.encode()).hexdigest() != w.get("hash"): raise ApiError("A source was altered after it was read. Add it again.")
    auth = trusted_authority(url, w.get("authority"))
    if w.get("authority") != auth: raise ApiError("A source failed its integrity check. Add it again.")
    d = None
    try: d = date.fromisoformat(w["date"]) if w.get("date") else None
    except (ValueError, TypeError): pass
    src = dict(id=sid, name=name, url=url, text=text, date=d, date_method=str(w.get("date_method", ""))[:40], authority=auth, error=None,
               injection=bool(T.INJ.search(text)), hash=w["hash"], retrieved_at=str(w.get("retrieved_at", ""))[:20], truncated=bool(w.get("truncated")))
    if os.environ.get("DARKSPOT_SECRET") and not hmac.compare_digest(sign({**wire(src), "date": str(d) if d else None}), str(w.get("sig", ""))):
        raise ApiError("A source failed its integrity check. Add it again.")
    src["undated"] = d is None
    src["stale"] = bool(d and (A.today() - d).days > A.STALE_DAYS)
    return src

def do_checklist(b):
    q, tpl = str(b.get("question", ""))[:300], b.get("template", "auto")
    if not q.strip(): raise ApiError("Enter a question.")
    if tpl != "auto" and tpl not in SCHEMAS: raise ApiError("Unknown topic.")
    llm = live(b.get("mode")); slots, origin = C.build(q, tpl, llm)
    out = dict(origin=origin, items=C.describe(slots), live=bool(llm), urls=[], warning="")
    if origin.startswith(("template:", "rules:")): out["template"] = origin.split(":")[1]
    if b.get("mode") == "claude" and not llm: out["warning"] = "Live reader unavailable (needs anthropic package, key and model). Using offline rules."
    if b.get("discover"):
        try: out["urls"] = net.discover(q, 3)
        except net.Blocked as e: out["warning"] = (out["warning"] + " " + str(e)).strip()
    return out

def do_sources(b):
    i, t = max(1, min(int(b.get("idx", 1) or 1), A.MAX_SOURCES)), A.today()
    if b.get("sample"):
        n = int(b["sample"])
        if not 1 <= n <= len(A.SAMPLE_SET): raise ApiError("Unknown sample.")
        return wire(A.sample_source(n, t) | {"id": f"S{i}"})
    if b.get("url"):
        u = str(b["url"])[:500]
        try:
            raw, final, trunc = net.fetch(u)
            s = A.make_source(i, re.sub(r"^https?://(www\.)?", "", final)[:60], final, raw, True, t); s["truncated"] = trunc
        except net.Blocked as e: s = A.failed(i, u[:60], u, str(e))
        return wire(s)
    if isinstance(b.get("pdf"), dict):
        f = b["pdf"]; name = str(f.get("name", ""))[:60] or f"PDF {i}"
        try: s = A.make_source(i, name, None, net.pdf_text(str(f.get("b64", ""))[:MAX_PDF]), False, t, "uploaded")
        except net.Blocked as e: s = A.failed(i, name, None, str(e))
        return wire(s)
    if str(b.get("text", "")).strip():
        return wire(A.make_source(i, str(b.get("name", ""))[:60] or f"Pasted text {i}", None, str(b["text"])[:MAX_TEXT], False, t))
    raise ApiError("Add a link, PDF or pasted text.")

def do_analyze(b):
    q = str(b.get("question", ""))[:300]
    if not q.strip(): raise ApiError("Enter a question.")
    slots = C.restore(b.get("checklist"))
    if not slots: raise ApiError("The checklist is missing or invalid.")
    raw = b.get("sources")
    if not isinstance(raw, list) or not raw: raise ApiError("Add at least one source.")
    if len(raw) > A.MAX_SOURCES: raise ApiError(f"Use at most {A.MAX_SOURCES} sources.")
    srcs = [from_wire(w, i) for i, w in enumerate(raw, 1)]
    origin = str(b["checklist"].get("origin", ""))[:60] or None
    return A.analyze(q, "auto", srcs, live(b.get("mode")), slots=slots, origin=origin, previous=b.get("previous"))

ROUTES = {"/api/checklist": do_checklist, "/api/sources": do_sources, "/api/analyze": do_analyze}

def send(h, code, obj, ctype="application/json; charset=utf-8"):
    b = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode()
    h.send_response(code)
    for k, v in (("Content-Type", ctype), ("Content-Length", str(len(b))), ("Content-Security-Policy", CSP), ("X-Content-Type-Options", "nosniff"),
                 ("Referrer-Policy", "no-referrer"), ("Cache-Control", "no-store")): h.send_header(k, v)
    h.end_headers(); h.wfile.write(b)

def serve(h, fn):
    # X-Forwarded-For is attacker-controlled unless a trusted proxy sets it; Vercel does, a bare local server does not.
    ip = ((h.headers.get("x-forwarded-for") if os.environ.get("VERCEL") else None) or h.client_address[0]).split(",")[0].strip()
    try:
        if (h.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
            raise ApiError("Content-Type must be application/json.", 415)    # also blocks cross-site simple requests (no CORS preflight possible)
        n = int(h.headers.get("Content-Length", 0))
        if n < 0: raise ApiError("Bad request.")
        if n > MAX_BODY: raise ApiError("Request too large.", 413)
        if limited(ip): raise ApiError("Too many requests. Wait a minute.", 429)
        body = json.loads(h.rfile.read(n) or b"{}")
        if not isinstance(body, dict): raise ApiError("Bad request.")
        send(h, 200, fn(body))
    except ApiError as e: send(h, e.code, {"error": str(e)})
    except (ValueError, TypeError, KeyError, RecursionError): send(h, 400, {"error": "Bad request."})
    except Exception: send(h, 500, {"error": "Something went wrong. Try again."})

def make_handler(fn):
    """One Vercel function = one class named `handler`."""
    class handler(BaseHTTPRequestHandler):
        def do_POST(self): serve(self, fn)
        def do_GET(self): send(self, 405, {"error": "Use POST."})
        def log_message(self, *a): pass
    return handler
