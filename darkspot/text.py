"""HTML to clean text, page-date detection, prompt-injection scan. Standard library only."""
import re
from html.parser import HTMLParser
from .facts import parse_dates

SKIP = {"script", "style", "noscript", "nav", "footer", "aside", "template", "svg"}
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr", "section", "article",
         "ul", "ol", "table", "header", "main", "dt", "dd", "blockquote"}
INJ = re.compile(r"ignore (all |any )?(previous|prior|above) instructions|disregard (the )?(above|previous)|"
                 r"you are now|system prompt|reveal your", re.I)

class _P(HTMLParser):
    def __init__(s):
        super().__init__(convert_charrefs=True)
        s.out, s.skip, s.meta, s.ld, s.times, s.cap, s.intitle = [], 0, {}, [], [], False, False
    def handle_starttag(s, t, a):
        a = dict(a)
        if t == "meta":
            k = (a.get("property") or a.get("name") or "").lower()
            if k and a.get("content"): s.meta[k] = a["content"]
        if t == "time" and a.get("datetime"): s.times.append(a["datetime"])
        if t == "script" and (a.get("type") or "").lower() == "application/ld+json":
            s.cap = True; s.ld.append("")
        if t == "title": s.intitle = True
        if t in SKIP: s.skip += 1
        if t in BLOCK: s.out.append("\n")
    def handle_endtag(s, t):
        if t in SKIP: s.skip = max(0, s.skip - 1)
        if t == "script": s.cap = False
        if t == "title": s.intitle = False
        if t in BLOCK: s.out.append("\n")
    def handle_data(s, d):
        if s.cap: s.ld[-1] += d
        elif not s.intitle and not s.skip: s.out.append(d)

def clean(raw):
    return "\n".join(l for l in (" ".join(x.split()) for x in raw.split("\n")) if l)

def _first(s):
    d = parse_dates(s)
    return d[0] if d else None

def page_date(text, meta, ld, times):
    for k in ("article:published_time", "og:updated_time", "article:modified_time", "date", "pubdate"):
        if k in meta and _first(meta[k]): return _first(meta[k]), "meta:" + k
    for blob in ld:
        m = re.search(r'"date(?:Published|Modified)"\s*:\s*"([^"]+)"', blob)
        if m and _first(m.group(1)): return _first(m.group(1)), "json-ld"
    for t in times:
        if _first(t): return _first(t), "time tag"
    for m in re.finditer(r"(?:published|posted|updated|dated)\b", text, re.I):
        d = _first(text[m.end():m.end() + 30].lstrip(" :-"))
        if d: return d, "text label"
    return None, "none found"

def parse_source(raw, is_html=True):
    """Returns dict(text, date, date_method, injection)."""
    if is_html and "<" in raw:
        p = _P(); p.feed(raw)
        text = clean("".join(p.out)); meta, ld, times = p.meta, p.ld, p.times
    else:
        text, meta, ld, times = clean(raw), {}, [], []
    d, method = page_date(text, meta, ld, times)
    return {"text": text, "date": d, "date_method": method, "injection": bool(INJ.search(text))}
