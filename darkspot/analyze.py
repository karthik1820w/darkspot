"""Pipeline: sources -> quotes -> verify -> compare -> gaps -> freshness -> ranked checklist."""
import os, re
from datetime import date, datetime
from pathlib import Path
from . import net, text as T
from .facts import SCHEMAS, RuleExtractor, normalise, show, verify

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SAMPLE_SET = [("Official notice", "https://foundation.example/aarohan", "official.html"),
              ("College page", "https://mycollege.example/scholarships", "college.html"),
              ("Blog post", "https://studyhelp.example/aarohan-guide", "blog.html")]
STALE_DAYS, MAX_SOURCES = 365, 6
RANK = {"conflict": 0, "gap": 1, "check": 1, "stale": 2, "single": 3, "confirmed": 9}
LABEL = {"conflict": "Conflict", "gap": "Missing", "check": "Unclear", "stale": "Possibly outdated",
         "single": "One page only", "confirmed": "Confirmed"}

def today():
    v = os.environ.get("DARKSPOT_TODAY")
    return datetime.strptime(v, "%Y-%m-%d").date() if v else date.today()

def make_source(i, name, url, raw, is_html, today_):
    s = T.parse_source(raw, is_html)
    s.update(id=f"S{i}", name=name, url=url, error=None)
    s["undated"] = s["date"] is None
    s["stale"] = bool(s["date"] and (today_ - s["date"]).days > STALE_DAYS)
    return s

def failed(i, name, url, msg):
    return {"id": f"S{i}", "name": name, "url": url, "text": "", "date": None, "date_method": "none found",
            "injection": False, "undated": True, "stale": False, "error": msg}

def load_sources(urls=(), texts=(), sample=False):
    t, out = today(), []
    if sample:
        for i, (n, u, f) in enumerate(SAMPLE_SET, 1):
            out.append(make_source(i, n, u, (SAMPLES / f).read_text(encoding="utf-8"), True, t))
        return out
    for u in urls:
        i = len(out) + 1
        try:
            raw, final, trunc = net.fetch(u)
            s = make_source(i, re.sub(r"^https?://(www\.)?", "", final)[:60], final, raw, True, t); s["truncated"] = trunc
        except net.Blocked as e:
            s = failed(i, u[:60], u, str(e))
        out.append(s)
    for n, raw in texts:
        out.append(make_source(len(out) + 1, n or f"Pasted text {len(out)+1}", None, raw, False, t))
    return out

def _ctx(text, q):
    i = text.find(q)
    clip = lambda x: " ".join(x.split())
    return clip(text[max(0, i - 80):i]), clip(text[i + len(q): i + len(q) + 80])

def analyze(question, template, sources, extractor=None):
    t, slots = today(), SCHEMAS[template]
    extractor = extractor or RuleExtractor()
    by_id, claims, dropped = {s["id"]: s for s in sources}, [], 0
    for s in sources:
        if s["error"] or not s["text"]: continue
        try: found = extractor.extract(s, slots)
        except Exception: found = []; s["error"] = "The reader could not process this source."
        for c in found:
            sl = next((x for x in slots if x["id"] == c["slot"]), None)
            if not sl or not verify(c, sl["kind"], s["text"]): dropped += 1; continue
            v = normalise(sl["kind"], c["quote"])
            stale = s["stale"] or (sl["kind"] == "date" and v < t)
            b, a = _ctx(s["text"], c["quote"])
            claims.append(dict(slot=c["slot"], source_id=s["id"], source_name=s["name"], quote=c["quote"], value=v,
                               display=show(sl["kind"], v), stale=stale, undated=s["undated"], before=b, after=a))
    items, confirmed = [], []
    for sl in slots:
        cs = [c for c in claims if c["slot"] == sl["id"]]
        item = dict(slot=sl["id"], label=sl["label"], verify=sl["verify"], claims=[], searched=[])
        fresh = [c for c in cs if not c["stale"]]
        stale = [c for c in cs if c["stale"]]
        distinct = {c["value"] for c in fresh}
        names = lambda L: ", ".join(sorted({c["source_name"] for c in L}))
        if not cs:
            hits = []
            for s in sources:
                m = re.search("|".join(map(re.escape, sl["terms"])), s["text"], re.I)
                if m:
                    q = next((x for x in re.split(r"\n", s["text"]) if m.group(0).lower() in x.lower()), "")
                    b, a = _ctx(s["text"], q)
                    hits.append(dict(slot=sl["id"], source_id=s["id"], source_name=s["name"], quote=q, display="", stale=False, undated=s["undated"], before=b, after=a))
            read = len([s for s in sources if s["text"]])
            if hits:
                item.update(state="check", summary="Related words appear but no clear statement was found. Read the quotes.", claims=hits[:2])
            else:
                item.update(state="gap", summary=f"Not found in the {read} pages reviewed (searched for: {', '.join(repr(x) for x in sl['terms'][:3])}).", searched=sl["terms"][:3])
        elif len(distinct) > 1:
            item.update(state="conflict", claims=cs, summary="Pages disagree: " + "; ".join(f"{c['source_name']} says {c['display']}" for c in fresh) + ".")
        elif stale:
            old = "; ".join(f"{c['source_name']} says {c['display']}" for c in stale)
            now_ = f" The newer page(s) say {fresh[0]['display']}." if fresh else " No current page confirms it."
            item.update(state="stale", claims=cs, summary=f"Possibly outdated: {old} (older page or past date).{now_}")
        elif len({c["source_id"] for c in fresh}) >= 2:
            item.update(state="confirmed", claims=cs, summary=f"Matches across {names(fresh)}: {fresh[0]['display']}.")
        else:
            item.update(state="single", claims=cs, summary=f"Only {fresh[0]['source_name']} covers this: {fresh[0]['display']}.")
        if item["state"] in ("conflict", "single") and any(c["undated"] for c in item["claims"]):
            item["summary"] += " At least one page shows no date."
        item.update(chip=LABEL[item["state"]], rank=RANK[item["state"]], w=sl["w"])
        (confirmed if item["state"] == "confirmed" else items).append(item)
    items.sort(key=lambda x: (x["rank"], -x["w"]))
    n = len(items)
    verdict = "Everything checked is confirmed across pages." if n == 0 else f"Not ready yet: {n} thing{'s' if n != 1 else ''} to verify"
    src_out = [{k: (str(s[k]) if k == "date" and s[k] else s[k]) for k in
                ("id", "name", "url", "date", "date_method", "undated", "stale", "injection", "error", "truncated") if k in s} for s in sources]
    for it in items + confirmed:
        for c in it["claims"]: c.pop("value", None)
        it.pop("w", None)
    return dict(question=question, template=template, today=str(t), extractor=extractor.name, verdict=verdict,
                note="Rule-based findings are signals, not facts. “Not found” means not found in these pages, not that it doesn’t exist.",
                items=items, confirmed=confirmed, sources=src_out, dropped=dropped)
