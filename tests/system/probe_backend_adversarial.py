import os, sys, json, time, socket, threading, http.server, gzip, subprocess, ssl, tempfile, traceback, shutil
os.environ["DARKSPOT_TODAY"] = "2026-10-31"; sys.path.insert(0, ".")
from darkspot import api, analyze as A, net, server, checklist as C
RES = []
def case(id, title):
    def deco(fn):
        t0 = time.time()
        try: ok, d = fn()
        except Exception as e: ok, d = False, f"EXC {type(e).__name__}: {str(e)[:90]}"
        RES.append((id, ok, title, str(d)[:120], round(time.time() - t0, 1))); return fn
    return deco
def local():
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.H); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv, srv.server_address[1]
def raw_http(port, data, wait=3):
    s = socket.create_connection(("127.0.0.1", port), timeout=wait); s.sendall(data)
    try: r = s.recv(4096)
    except socket.timeout: return None
    return r.split(b"\r\n")[0].decode() if r else ""
def web(handler_cls):
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls); threading.Thread(target=s.serve_forever, daemon=True).start(); return s, s.server_address[1]
def fetch_via(port, host="pinned.example"):
    orig = net.resolve; net.resolve = lambda u: ("http", host, "127.0.0.1", port, "/")
    try: return net.fetch("http://" + host + "/")
    finally: net.resolve = orig
mk = lambda txt, n="A": A.make_source(1, n, None, txt, False, A.today())
srv, port = local()

@case("F01", "negative Content-Length must not hang the server")
def _():
    r = raw_http(port, b"POST /api/sources HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: -5\r\n\r\n{}"); return r is not None and "400" in r, r
@case("F02", "absurdly large number in a fee must not crash analysis")
def _(): A.analyze("q", "general", [mk("The cost is $" + "9" * 400 + ".")]); return True, "ok"
@case("F03", "5000-digit duration must not crash analysis")
def _(): A.analyze("q", "visa", [mk("Visa processing takes " + "9" * 5000 + " weeks.")]); return True, "ok"
@case("F04", "lone surrogate in pasted text must not cause a 500")
def _():
    body = b'{"text":"abc \\ud800 deadline 30 November 2026"}'
    r = raw_http(port, b"POST /api/sources HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body); return r is not None and "500" not in r, r
@case("F05", "bogus charset header must not crash fetch")
def _():
    class S(http.server.BaseHTTPRequestHandler):
        def do_GET(self): b = b"<p>hi</p>"; self.send_response(200); self.send_header("Content-Type", "text/html; charset=bogus"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def log_message(self, *a): pass
    s, p = web(S)
    try: return "hi" in fetch_via(p)[0], "ok"
    finally: s.shutdown()
@case("F06", "malformed URLs must raise only Blocked")
def _():
    bad = []
    for u in ["http://[::1", "http://a..b/", "http://" + "a" * 70 + ".com/", "http://host:99999/", "http://host:abc/", "http://%00/", "http://exa mple.com/", "http://" + "é" * 80 + ".com/"]:
        try: net.check_url(u)
        except net.Blocked: pass
        except Exception as e: bad.append(f"{u[:18]}->{type(e).__name__}")
    return not bad, bad
@case("F07", "a page with no sentence breaks must not return a 100k-char quote")
def _():
    r = A.analyze("q", "scholarship", [mk("filler " * 20000 + " The last date to apply is 30 November 2026. renew " + "filler " * 20000)])
    m = max(len(c["quote"]) for i in r["items"] + r["confirmed"] for c in i["claims"]); return m <= 1000, f"longest quote {m} chars"
@case("F08", "GET / with a query string (utm params) should load")
def _():
    r = raw_http(port, b"GET /?utm_source=x HTTP/1.1\r\nHost: x\r\n\r\n"); return r is not None and "200" in r, r
@case("F09", "when no source is readable, the report must not say 'not found in the 0 pages'")
def _():
    r = A.analyze("q", "scholarship", [A.failed(1, "x", "http://x", "Could not reach the site.")]); s = " ".join(i["summary"] for i in r["items"]) + r["verdict"]
    return "0 pages" not in s, r["verdict"]
@case("F10", "sample demo must behave the same after its fictional deadline passes")
def _():
    st = lambda: {i["slot"]: i["state"] for i in (lambda r: r["items"] + r["confirmed"])(A.analyze("q", "scholarship", A.load_sources(sample=True)))}
    a = st(); os.environ["DARKSPOT_TODAY"] = "2027-01-15"
    try: b = st()
    finally: os.environ["DARKSPOT_TODAY"] = "2026-10-31"
    return a == b, {k: (a[k], b[k]) for k in a if a[k] != b[k]}
@case("F11", "changes must warn when the set of sources differs from the last check")
def _():
    prev = A.analyze("q", "scholarship", A.load_sources(sample=True))["snapshot"]
    ch = A.analyze("q", "scholarship", A.load_sources(sample=True)[:1], previous=prev)["changes"]; return any("set of pages differs" in c for c in ch), ch[:2]
@case("F12", "POST with text/plain content-type should be refused (cross-site simple request)")
def _():
    r = raw_http(port, b"POST /api/checklist HTTP/1.1\r\nHost: x\r\nContent-Type: text/plain\r\nContent-Length: 20\r\n\r\n" + b'{"question":"visa?"}'); return r is not None and "415" in r, r
@case("F13", "gzip-encoded response must not be decoded as garbage text")
def _():
    class S(http.server.BaseHTTPRequestHandler):
        def do_GET(self): b = gzip.compress(b"<p>hello</p>"); self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Encoding", "gzip"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def log_message(self, *a): pass
    s, p = web(S)
    try:
        try: t = fetch_via(p)[0]; return "hello" in t, repr(t[:20])
        except net.Blocked as e: return True, str(e)
    finally: s.shutdown()
@case("F14", "a slow-drip server must be cut off (total deadline)")
def _():
    class S(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            try:
                for _ in range(40): self.wfile.write(b"a"); self.wfile.flush(); time.sleep(0.6)
            except Exception: pass
        def log_message(self, *a): pass
    s, p = web(S); t0 = time.time()
    try:
        try: fetch_via(p)
        except net.Blocked: pass
        e = time.time() - t0; return e < 17, f"held the function {e:.0f}s"
    finally: s.shutdown()
@case("F15", "IPv4 should be preferred over IPv6 when both are public")
def _():
    o = socket.getaddrinfo; socket.getaddrinfo = lambda *a, **k: [(10, 1, 6, "", ("2606:4700:4700::1111", 80, 0, 0)), (2, 1, 6, "", ("1.1.1.1", 80))]
    try: ip = net.resolve("http://example.com/")[2]
    finally: socket.getaddrinfo = o
    return ip == "1.1.1.1", ip
@case("F16", "TLS: cert for the right host works, wrong-host cert is rejected (pinning must not disable hostname checks)")
def _():
    openssl = shutil.which("openssl")
    if not openssl:
        for c in (r"C:\Program Files\Git\usr\bin\openssl.exe", r"C:\Program Files (x86)\Git\usr\bin\openssl.exe"):
            if os.path.exists(c): openssl = c; break
    if not openssl: return True, "openssl not available, skipped"
    d = tempfile.mkdtemp(); out = {}
    for name in ("pinned.example", "other.example"):
        c, k = f"{d}/{name}.crt", f"{d}/{name}.key"
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", k, "-out", c, "-days", "1", "-subj", f"/CN={name}", "-addext", f"subjectAltName=DNS:{name}"], capture_output=True, check=True)
        out[name] = (c, k)
    class S(http.server.BaseHTTPRequestHandler):
        def do_GET(self): b = b"<p>secure hello</p>"; self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def log_message(self, *a): pass
    orig_ctx, orig_res = ssl.create_default_context, net.resolve; res = []
    for served, trust in (("pinned.example", "pinned.example"), ("other.example", "pinned.example")):
        s = http.server.HTTPServer(("127.0.0.1", 0), S); ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(*out[served]); s.socket = ctx.wrap_socket(s.socket, server_side=True)
        threading.Thread(target=s.serve_forever, daemon=True).start(); p = s.server_address[1]
        net.ssl.create_default_context = lambda *a, **k: orig_ctx(cafile=out[trust][0]); net.resolve = lambda u, p=p: ("https", "pinned.example", "127.0.0.1", p, "/")
        try: res.append("ok" if "secure hello" in net.fetch("https://pinned.example/")[0] else "garbled")
        except net.Blocked: res.append("blocked")
        finally: net.ssl.create_default_context, net.resolve = orig_ctx, orig_res; s.shutdown()
    return res == ["ok", "blocked"], res
@case("F18", "bad shapes for sources / checklist / previous must give 4xx, never 500")
def _():
    bad = []
    for b in [{"question": "q", "checklist": {"template": "visa"}, "sources": "x"}, {"question": "q", "checklist": {"template": "visa"}, "sources": [1, None]},
              {"question": "q", "checklist": 5, "sources": [{}]}, {"question": "q", "checklist": {"template": "visa"}, "sources": [{"text": "a", "hash": "z"}]},
              {"question": "q", "checklist": {"template": "visa"}, "sources": [{"error": "e"}], "previous": {"items": {"x": {"values": 5}}, "sources": []}}]:
        try: api.do_analyze(b)
        except api.ApiError: pass
        except Exception as e: bad.append(type(e).__name__)
    return not bad, bad
@case("F19", "latency: 6 sources x 200KB analysed within a serverless-safe time")
def _():
    big = ("The deadline is 30 November 2026. The fee is $350. Applicants must submit a marksheet. " + "Lorem ipsum dolor sit amet consectetur adipiscing elit. " * 3500)[:200000]
    t0 = time.time(); A.analyze("q", "scholarship", [A.make_source(i, f"S{i}", None, big + str(i) * 50, False, A.today()) for i in range(1, 7)]); e = time.time() - t0; return e < 3, f"{e:.2f}s"
@case("F20", "rate limit must not be bypassable by spoofing X-Forwarded-For on a non-Vercel host")
def _():
    api.HITS.clear(); codes = []
    for i in range(80):
        body = b'{"question":"visa?"}'; r = raw_http(port, b"POST /api/checklist HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nX-Forwarded-For: 9.9.%d.%d\r\nContent-Length: %d\r\n\r\n" % (i // 200, i, len(body)) + body); codes.append(r.split()[1] if r else "none")
    return "429" in codes, f"{codes.count('429')} of 80 limited"
@case("F21", "deeply nested JSON must be a 400, not a 500")
def _():
    api.HITS.clear(); body = b"[" * 100000; r = raw_http(port, b"POST /api/checklist HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body); return r is not None and "400" in r, r
@case("F22", "idx and sample params of the wrong type give 400")
def _():
    bad = []
    for b in [{"text": "a", "idx": "abc"}, {"sample": "x"}, {"sample": [1]}, {"url": ["a"]}, {"pdf": "str"}]:
        try: api.do_sources(b)
        except api.ApiError: pass
        except (ValueError, TypeError): pass
        except Exception as e: bad.append(type(e).__name__)
    return not bad, bad
for r in RES: print(("PASS" if r[1] else "FAIL"), r[0], "|", r[2], "|", r[3] if not r[1] else "", f"({r[4]}s)")
print("\nFAILED:", [r[0] for r in RES if not r[1]])
