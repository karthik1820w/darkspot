"""Pipeline: sources -> quotes -> verify -> compare -> gaps -> freshness -> confidence -> ranked checklist.
emit(stage, message) reports progress so the UI can stream it (stages 4-6 here; 1-3 in the server)."""
import os, re, urllib.parse
from datetime import date, datetime
from pathlib import Path
from . import net, text as T
from .facts import SCHEMAS, RuleExtractor, normalise, show, verify, negated

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SAMPLE_SET = [("Official notice", "https://foundation.example/aarohan", "official.html", "official"),
              ("College page", "https://mycollege.example/scholarships", "college.html", "institution"),
              ("Blog post", "https://studyhelp.example/aarohan-guide", "blog.html", "community")]
STALE_DAYS, MAX_SOURCES = 365, 6
RANK = {"conflict": 0, "gap": 1, "check": 1, "stale": 2, "single": 3, "confirmed": 9}
LABEL = {"conflict": "Conflict", "gap": "Missing", "check": "Unclear", "stale": "Possibly outdated",
         "single": "One page only", "confirmed": "Confirmed"}
AUTH = {"official": 3, "institution": 2, "third-party": 1, "pasted": 1, "uploaded": 1, "community": 0, "unknown": 0}
ASK = {"gap": "Ask the provider directly: “{l}?”", "conflict": "Email the official source quoting both versions and ask which is current.",
       "stale": "Ask whether this changed for the current cycle.", "check": "Read the highlighted lines; ask the provider if still unclear.",
       "single": "Look for a second, independent source before relying on it.", "confirmed": ""}
noop = lambda stage, msg: None

def today():
    v = os.environ.get("DARKSPOT_TODAY")
    return datetime.strptime(v, "%Y-%m-%d").date() if v else date.today()

def authority(url):
    """Heuristic from the domain only. It cannot prove a site is official; the UI says so."""
    if not url: return "pasted"
    h = (urllib.parse.urlsplit(url).hostname or "").lower()
    if re.search(r"(^|\.)(gov|nic|mil)(\.[a-z]{2})?$", h): return "official"
    if re.search(r"(^|\.)(edu|ac)(\.[a-z]{2})?$", h): return "institution"
    if re.search(r"blog|medium\.com|reddit|quora|forum|wordpress|substack", h): return "community"
    return "third-party"

def make_source(i, name, url, raw, is_html, today_, auth=None):
    s = T.parse_source(raw, is_html)
    s.update(id=f"S{i}", name=name, url=url, error=None, authority=auth or authority(url))
    s["undated"] = s["date"] is None
    s["stale"] = bool(s["date"] and (today_ - s["date"]).days > STALE_DAYS)
    return s

def failed(i, name, url, msg):
    return {"id": f"S{i}", "name": name, "url": url, "text": "", "date": None, "date_method": "none found", "injection": False,
            "undated": True, "stale": False, "error": msg, "authority": "unknown"}

def load_sources(urls=(), texts=(), pdfs=(), sample=False, emit=noop):
    t, out = today(), []
    if sample:
        for i, (n, u, f, a) in enumerate(SAMPLE_SET, 1):
            emit(3, f"Reading sample page: {n}")
            out.append(make_source(i, n, u, (SAMPLES / f).read_text(encoding="utf-8"), True, t, a))
        return out
    for u in urls:
        i = len(out) + 1; emit(3, f"Fetching {urllib.parse.urlsplit(u).hostname or u[:40]}")
        try:
            raw, final, trunc = net.fetch(u)
            s = make_source(i, re.sub(r"^https?://(www\.)?", "", final)[:60], final, raw, True, t); s["truncated"] = trunc
        except net.Blocked as e:
            s = failed(i, u[:60], u, str(e))
        out.append(s)
    for n, b64 in pdfs:
        i = len(out) + 1; emit(3, f"Reading PDF: {n or 'upload'}")
        try: out.append(make_source(i, n or f"PDF {i}", None, net.pdf_text(b64), False, t, "uploaded"))
        except net.Blocked as e: out.append(failed(i, n or f"PDF {i}", None, str(e)))
    for n, raw in texts:
        out.append(make_source(len(out) + 1, n or f"Pasted text {len(out)+1}", None, raw, False, t))
    return out

def _ctx(text, q):
    i = text.find(q); clip = lambda x: " ".join(x.split())
    return clip(text[max(0, i - 80):i]), clip(text[i + len(q): i + len(q) + 80])

def confidence(state, cs):
    r = max((AUTH[c["authority"]] for c in cs), default=0)
    if state == "confirmed": return ("high", "2+ pages agree, one looks official") if r >= 2 else ("medium", "2+ pages agree, none look official")
    if state == "single": return ("medium", "one official-looking page, uncorroborated") if r == 3 else ("low", "one page only")
    if state == "gap": return ("none", "not found in the pages reviewed")
    return ("low", {"conflict": "pages disagree", "stale": "date is old or past", "check": "no clear statement found"}[state])

def _top(cs):
    ranks = {AUTH[c["authority"]] for c in cs}
    if len(ranks) < 2: return None
    best = {c["source_name"] for c in cs if AUTH[c["authority"]] == max(ranks)}
    return next(iter(best)) if len(best) == 1 and max(ranks) > 0 else None

def analyze(question, template, sources, extractor=None, emit=noop, slots=None, origin=None):
    t, slots = today(), slots or SCHEMAS[template]
    extractor = extractor or RuleExtractor()
    claims, dropped = [], 0
    for s in sources:
        if s["error"] or not s["text"]: continue
        emit(4, f"Extracting quotes from {s['name']} ({extractor.name})")
        try: found = extractor.extract(s, slots)
        except Exception: found = []; s["error"] = "The reader could not process this source."
        for c in found:
            sl = next((x for x in slots if x["id"] == c["slot"]), None)
            if not sl or not verify(c, sl["kind"], s["text"]): dropped += 1; continue
            v = normalise(sl["kind"], c["quote"]); b, a = _ctx(s["text"], c["quote"])
            claims.append(dict(slot=c["slot"], source_id=s["id"], source_name=s["name"], authority=s["authority"], quote=c["quote"], value=v,
                               display=show(sl["kind"], v), stale=s["stale"] or (sl["kind"] == "date" and v < t), undated=s["undated"],
                               neg=sl["kind"] in ("docs", "text") and negated(c["quote"]), before=b, after=a))
    emit(4, f"{len(claims)} quotes verified verbatim against stored page text" + (f"; {dropped} rejected" if dropped else ""))
    emit(5, "Comparing sources, checking dates, searching for gaps")
    items, confirmed = [], []
    for sl in slots:
        cs = [c for c in claims if c["slot"] == sl["id"]]
        item = dict(slot=sl["id"], label=sl["label"], verify=sl["verify"], claims=[], searched=[], origin="derived")
        fresh, stale = [c for c in cs if not c["stale"]], [c for c in cs if c["stale"]]
        pos, ng = [c for c in fresh if not c["neg"]], [c for c in fresh if c["neg"]]
        distinct = {c["value"] for c in pos}
        names = lambda L: ", ".join(sorted({c["source_name"] for c in L}))
        if not cs:
            hits = []
            for s in sources:
                m = re.search("|".join(map(re.escape, sl["terms"])), s["text"], re.I)
                if m:
                    q = next((x for x in s["text"].split("\n") if m.group(0).lower() in x.lower()), "")
                    b, a = _ctx(s["text"], q)
                    hits.append(dict(slot=sl["id"], source_id=s["id"], source_name=s["name"], authority=s["authority"], quote=q, display="", stale=False,
                                     undated=s["undated"], neg=False, before=b, after=a))
            read = len([s for s in sources if s["text"]])
            if hits: item.update(state="check", summary="Related words appear but no clear statement was found. Read the quotes.", claims=hits[:2])
            else: item.update(state="gap", summary=f"Not found in the {read} pages reviewed (searched for: {', '.join(repr(x) for x in sl['terms'][:3])}).", searched=sl["terms"][:3])
        elif ng and pos:
            item.update(state="conflict", claims=cs, summary=f"Wording differs: {names(pos)} state it, but {names(ng)} negate or relax it (see quotes).")
        elif ng:
            item.update(state="check", claims=cs, summary=f"Only negated or optional wording found in {names(ng)}. Read the quote.")
        elif len(distinct) > 1:
            top = _top(fresh)
            item.update(state="conflict", claims=cs, summary="Pages disagree: " + "; ".join(f"{c['source_name']} says {c['display']}" for c in fresh) + "."
                        + (f" Highest-authority source by domain heuristic: {top}; still verify." if top else ""))
        elif stale:
            old = "; ".join(f"{c['source_name']} says {c['display']}" for c in stale)
            now_ = f" The newer page(s) say {fresh[0]['display']}." if fresh else " No current page confirms it."
            item.update(state="stale", claims=cs, summary=f"Possibly outdated: {old} (older page or past date).{now_}")
        elif len({c["source_id"] for c in fresh}) >= 2:
            item.update(state="confirmed", claims=cs, summary=f"Matches across {names(fresh)}: {fresh[0]['display']}.")
        else:
            item.update(state="single", claims=cs, summary=f"Only {fresh[0]['source_name']} covers this: {fresh[0]['display']}.")
        if item["state"] in ("conflict", "single") and any(c["undated"] for c in item["claims"]): item["summary"] += " At least one page shows no date."
        cf, why = confidence(item["state"], item["claims"])
        item.update(chip=LABEL[item["state"]], rank=RANK[item["state"]], w=sl["w"], confidence=cf, confidence_why=why,
                    ask=ASK[item["state"]].format(l=sl["label"]))
        (confirmed if item["state"] == "confirmed" else items).append(item)
    items.sort(key=lambda x: (x["rank"], -x["w"]))
    n = len(items)
    verdict = "Everything checked is confirmed across pages." if n == 0 else f"Not ready yet: {n} thing{'s' if n != 1 else ''} to verify"
    keys = ("id", "name", "url", "date", "date_method", "undated", "stale", "injection", "error", "truncated", "authority")
    src_out = [{k: (str(s[k]) if k == "date" and s[k] else s[k]) for k in keys if k in s} for s in sources]
    found = len([i for i in items + confirmed if i["state"] not in ("gap", "check")])
    for it in items + confirmed:
        for c in it["claims"]: c.pop("value", None)
        it.pop("w", None)
    emit(6, "Building dashboard")
    return dict(question=question, template=template, today=str(t), extractor=extractor.name, checklist_origin=origin or "template:" + template,
                verdict=verdict, meter=dict(total=len(slots), found=found, corroborated=len(confirmed), to_verify=n),
                note="Findings are signals from rules or AI, not facts. “Not found” means not found in these pages, not that it doesn’t exist. "
                     "Source authority is guessed from the domain and can be wrong.",
                items=items, confirmed=confirmed, sources=src_out, dropped=dropped)
