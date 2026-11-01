"""Safe fetching. Resolve ONCE, validate every address, then connect to that exact IP (closes the DNS-rebinding race).
Scheme/port allowlist, no private IPs, manual redirects (each hop re-validated), size and time caps."""
import http.client, ipaddress, socket, ssl, time, urllib.parse, urllib.request
MAX_BYTES, TIMEOUT, DEADLINE = 1_500_000, 8, 15   # DEADLINE: total seconds for one fetch incl. redirects
OK_TYPES = ("text/html", "text/plain", "application/xhtml+xml")

class Blocked(Exception):
    """Message is safe to show to the user."""

def resolve(url):
    """Returns (scheme, host, ip, port, target). Every resolved address must be public."""
    try: p = urllib.parse.urlsplit(url); host, port = p.hostname, p.port
    except ValueError: raise Blocked("That link is not valid.")
    if p.scheme not in ("http", "https") or not host: raise Blocked("Only http and https links are allowed.")
    if p.username or p.password: raise Blocked("Links with a username or password are not allowed.")
    port = port or (443 if p.scheme == "https" else 80)
    if port not in (80, 443): raise Blocked("Only ports 80 and 443 are allowed.")
    try: infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror: raise Blocked("Could not find that address.")
    except (UnicodeError, ValueError): raise Blocked("That link is not valid.")
    ips = sorted((i[4][0].split("%")[0] for i in infos), key=lambda x: ":" in x)   # IPv4 first: more reliable on serverless networks
    if not ips or not all(ipaddress.ip_address(x).is_global for x in ips): raise Blocked("That address points to a private or local network.")
    return p.scheme, host, ips[0], port, (p.path or "/") + ("?" + p.query if p.query else "")

def check_url(url):
    resolve(url); return url

def _get(scheme, host, ip, port, target):
    """One GET to the pinned ip. TLS still verifies the certificate against the hostname."""
    if scheme == "https":
        ctx = ssl.create_default_context()
        class Conn(http.client.HTTPSConnection):
            def connect(self):
                self.sock = ctx.wrap_socket(socket.create_connection((ip, port), TIMEOUT), server_hostname=host)
        c = Conn(host, port, timeout=TIMEOUT, context=ctx)
    else:
        class Conn(http.client.HTTPConnection):
            def connect(self): self.sock = socket.create_connection((ip, port), TIMEOUT)
        c = Conn(host, port, timeout=TIMEOUT)
    c.request("GET", target, headers={"User-Agent": "DarkSpot/0.2 research prototype", "Accept": "text/html,text/plain", "Accept-Encoding": "identity"})
    return c, c.getresponse()

def fetch(url, hops=3):
    """Returns (text, final_url, truncated). Every redirect hop is re-resolved and re-validated."""
    end = time.monotonic() + DEADLINE
    for _ in range(hops + 1):
        if time.monotonic() > end: raise Blocked("The site was too slow to respond.")
        scheme, host, ip, port, target = resolve(url)
        try:
            c, r = _get(scheme, host, ip, port, target)
            try:
                if r.status in (301, 302, 303, 307, 308) and r.getheader("Location"):
                    url = urllib.parse.urljoin(url, r.getheader("Location")); continue
                if r.status >= 400: raise Blocked(f"The site returned error {r.status}.")
                ctype = (r.getheader("Content-Type") or "").split(";")[0].strip().lower()
                if ctype not in OK_TYPES: raise Blocked("Only web pages and plain text work. Paste the text instead.")
                if (r.getheader("Content-Encoding") or "identity").lower() != "identity":
                    raise Blocked("The site sent compressed data this tool cannot read. Paste the text instead.")
                raw = b""
                while len(raw) <= MAX_BYTES:                       # read1 returns as soon as data arrives, so the deadline is enforced
                    if time.monotonic() > end: raise Blocked("The site was too slow to respond.")
                    chunk = r.read1(65536)
                    if not chunk: break
                    raw += chunk
                body = raw[:MAX_BYTES]
                try: text = body.decode(r.headers.get_content_charset() or "utf-8", "replace")
                except LookupError: text = body.decode("utf-8", "replace")     # unknown charset name in the header
                return text, url, len(raw) > MAX_BYTES
            finally: c.close()
        except Blocked: raise
        except (OSError, http.client.HTTPException): raise Blocked("Could not reach the site.")
    raise Blocked("Too many redirects.")

def pdf_text(b64, max_pages=30):
    """Stage 3: text layer of an uploaded PDF. Needs the optional pypdf package. Scans/encrypted files are refused, not guessed."""
    try: from pypdf import PdfReader
    except ImportError: raise Blocked("PDF reading needs: pip install pypdf")
    import base64, io
    try:
        raw = base64.b64decode(b64, validate=True)
        if raw[:5] != b"%PDF-": raise ValueError
        r = PdfReader(io.BytesIO(raw))
        if r.is_encrypted: raise Blocked("Encrypted PDFs are not supported.")
        t = "\n".join((p.extract_text() or "") for p in r.pages[:max_pages])
    except Blocked: raise
    except Exception: raise Blocked("Could not read that PDF.")
    if not t.strip(): raise Blocked("This PDF has no text layer (scanned?). Paste the text instead.")
    return t

def discover(q, n=3):
    """Optional search discovery via Brave Search API (BRAVE_API_KEY). WRITTEN TO THE DOCUMENTED FORMAT, NOT RUN
    in the build sandbox. Returned URLs still go through fetch(), so the SSRF checks apply."""
    import json, os
    key = os.environ.get("BRAVE_API_KEY")
    if not key: raise Blocked("Search discovery is off: set BRAVE_API_KEY.")
    req = urllib.request.Request("https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": q[:200], "count": n}),
                                 headers={"X-Subscription-Token": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r: d = json.load(r)
    except Exception: raise Blocked("Search request failed.")
    return [x["url"] for x in d.get("web", {}).get("results", []) if x.get("url")][:n]
