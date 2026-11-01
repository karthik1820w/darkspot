"""Safe fetching: scheme/port allowlist, DNS check, no private IPs, manual redirects, size and time caps."""
import ipaddress, socket, urllib.error, urllib.parse, urllib.request
MAX_BYTES, TIMEOUT = 1_500_000, 8
OK_TYPES = ("text/html", "text/plain", "application/xhtml+xml")

class Blocked(Exception):
    """Message is safe to show to the user."""

def check_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise Blocked("Only http and https links are allowed.")
    if p.username or p.password:
        raise Blocked("Links with a username or password are not allowed.")
    port = p.port or (443 if p.scheme == "https" else 80)
    if port not in (80, 443):
        raise Blocked("Only ports 80 and 443 are allowed.")
    try:
        infos = socket.getaddrinfo(p.hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise Blocked("Could not find that address.")
    for i in infos:
        if not ipaddress.ip_address(i[4][0].split("%")[0]).is_global:
            raise Blocked("That address points to a private or local network.")
    return url

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None

def fetch(url, hops=3):
    """Returns (text, final_url, truncated). Every redirect hop is re-validated."""
    opener = urllib.request.build_opener(_NoRedirect)
    for _ in range(hops + 1):
        check_url(url)
        req = urllib.request.Request(url, headers={"User-Agent": "DarkSpot/0.1 research prototype"})
        try:
            r = opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            raise Blocked(f"The site returned error {e.code}.")
        except (urllib.error.URLError, socket.timeout, TimeoutError):
            raise Blocked("Could not reach the site.")
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in OK_TYPES:
            raise Blocked("Only web pages and plain text work. Paste the text instead.")
        raw = r.read(MAX_BYTES + 1)
        return raw[:MAX_BYTES].decode(r.headers.get_content_charset() or "utf-8", "replace"), url, len(raw) > MAX_BYTES
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
