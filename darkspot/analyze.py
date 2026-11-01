"""Pipeline: sources -> quotes -> verify -> compare -> gaps -> freshness -> confidence -> ranked checklist.
emit(stage, message) reports progress so the UI can stream it (stages 4-6 here; 1-3 in the server)."""
import hashlib, os, re, urllib.parse
from datetime import date, datetime, timedelta, timezone
from . import net, samples as SM, signals as SG, text as T
from .facts import SCHEMAS, RuleExtractor, normalise, show, verify, negated

SAMPLE_SET = [("Official notice", "https://foundation.example/aarohan", "official", "official"),
              ("College page", "https://mycollege.example/scholarships", "college", "institution"),
              ("Blog post", "https://studyhelp.example/aarohan-guide", "blog", "community")]
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

def val(c):
    """Value to show inside a sentence: the parsed value, or a short quote for free-text items (whose parsed value is just 'stated')."""
    if c["display"] != "stated": return c["display"]
    q = c["quote"]; return "“" + q[:70] + ("…" if len(q) > 70 else "") + "”"

def make_source(i, name, url, raw, is_html, today_, auth=None):
    s = T.parse_source(raw, is_html)
    s.update(id=f"S{i}", name=name, url=url, error=None, authority=auth or authority(url))
    s["undated"] = s["date"] is None
    s["stale"] = bool(s["date"] and (today_ - s["date"]).days > STALE_DAYS)
    s["hash"] = hashlib.sha256(s["text"].encode()).hexdigest()          # evidence receipt: what exactly was read
    s["retrieved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return s

def failed(i, name, url, msg):
    return {"id": f"S{i}", "name": name, "url": url, "text": "", "date": None, "date_method": "none found", "injection": False,
            "undated": True, "stale": False, "error": msg, "authority": "unknown"}

SAMPLE_DATES = {"12 August 2026": -80, "30 November 2026": 30, "3 October 2024": -760, "15 December 2024": -700}   # days from today

def sample_source(i, t=None):
    """Fictional pages whose dates move with today, so the demo story never expires."""
    t = t or today(); n, u, k, a = SAMPLE_SET[i - 1]; html = SM.PAGES[k]
    for old, off in SAMPLE_DATES.items(): d = t + timedelta(days=off); html = html.replace(old, f"{d.day} {d.strftime('%B %Y')}")
    return make_source(i, n, u, html, True, t, a)

def load_sources(urls=(), texts=(), pdfs=(), sample=False, emit=noop):
    t, out = today(), []
    if sample: return [sample_source(i, t) for i in range(1, len(SAMPLE_SET) + 1)]
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

def _ctx(text, q, n=80):
    """Up to n characters of surrounding text, trimmed so a snippet never starts or ends in the middle of a word."""
    i = text.find(q); j = i + len(q); clip = lambda x: " ".join(x.split())
    before, after = text[max(0, i - n):i], text[j:j + n]
    if i - n > 0 and not text[i - n - 1].isspace() and before and not before[0].isspace(): before = before.partition(" ")[2]
    if len(text) > j + n and not text[j + n].isspace() and after and not after[-1].isspace(): after = after.rpartition(" ")[0]
    return clip(before), clip(after)

def confidence(state, cs):
    r = max((AUTH[c["authority"]] for c in cs), default=0)
    if state == "confirmed": return ("high", "2+ pages agree, one looks official") if r >= 2 else ("medium", "2+ pages agree, none look official")
    if state == "single": return ("medium", "one official-looking page, uncorroborated") if r == 3 else ("low", "one page only")
    if state == "gap": return ("none", "not found in the pages reviewed")
    return ("low", {"conflict": "pages disagree", "stale": "date is old or past", "check": "needs a human read"}[state])

def _top(cs):
    ranks = {AUTH[c["authority"]] for c in cs}
    if len(ranks) < 2: return None
    best = {c["source_name"] for c in cs if AUTH[c["authority"]] == max(ranks)}
    return next(iter(best)) if len(best) == 1 and max(ranks) > 0 else None

def clusters(sources, thr=0.6, min_sh=15):
    """Group pages whose text largely overlaps (5-word shingle containment). Copies are not independent confirmation."""
    sh = {}
    for s in sources:
        w = re.findall(r"\w+", s["text"].lower())
        sh[s["id"]] = {" ".join(w[i:i + 5]) for i in range(max(0, len(w) - 4))} if len(w) >= min_sh + 4 else set()
    root = {s["id"]: s["id"] for s in sources}
    def find(x):
        while root[x] != x: x = root[x]
        return x
    ids = list(root)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            x, y = sh[a], sh[b]
            if x and y and len(x & y) / min(len(x), len(y)) >= thr: root[find(b)] = find(a)
    return {i: find(i) for i in ids}

CREDIT = {"confirmed": 1.0, "single": 0.5, "stale": 0.25, "check": 0.1, "conflict": 0.0, "gap": 0.0}

def readiness(items):
    tot = sum(i["w"] for i in items) or 1
    pct = round(100 * sum(i["w"] * CREDIT[i["state"]] for i in items) / tot)
    return dict(pct=pct, band="Mostly ready" if pct >= 85 else "Partly ready" if pct >= 50 else "Not ready",
                rule="Heuristic: confirmed 100%, one page 50%, outdated 25%, unclear 10%, conflict or missing 0%, weighted by importance.")

def snapshot(items, sources, t):
    return dict(at=str(t), items={i["slot"]: dict(label=i["label"], state=i["state"], values=sorted({c["display"] for c in i["claims"] if c["display"]})[:6]) for i in items},
                sources={(s["url"] or s["name"])[:200]: s["hash"] for s in sources if s.get("hash")})

def diff(prev, now):
    """What changed since the user's last check. `prev` is client-supplied, so it is shape-checked and never trusted for anything but display."""
    if not (isinstance(prev, dict) and isinstance(prev.get("items"), dict) and isinstance(prev.get("sources"), dict)): return None
    ch = []
    a, b = set(prev["sources"]), set(now["sources"])
    if a != b: ch.append(f"The set of pages differs from your last check ({len(b - a)} added, {len(a - b)} removed), so some differences below may come from that and not from the pages changing.")
    for slot, cur in now["items"].items():
        p = prev["items"].get(slot)
        if not isinstance(p, dict) or not isinstance(p.get("values"), list): continue
        if p.get("state") != cur["state"]: ch.append(f"{cur['label']}: {LABEL.get(p.get('state'), '?')} → {LABEL[cur['state']]}")
        elif [str(v)[:60] for v in p["values"]] != cur["values"]: ch.append(f"{cur['label']}: value changed from {', '.join(str(v)[:60] for v in p['values']) or 'none'} to {', '.join(cur['values']) or 'none'}")
    for k, h in now["sources"].items():
        if prev["sources"].get(k) not in (None, h): ch.append(f"Page content changed since your last check: {k}")
    return ch

def email_draft(question, items):
    """Plain template, no AI: turns open findings into questions for the provider."""
    todo = [i for i in items if i["state"] != "confirmed"]
    if not todo: return ""
    say = {"gap": "I could not find this in the pages I reviewed.", "conflict": "the sources I found disagree.", "stale": "the page I found may be out of date.",
           "single": "I found it on only one page and want to confirm it.", "check": "the wording I found was unclear."}
    lines = [f"{n}. {i['label']}: " + (say[i["state"]][0].upper() + say[i["state"]][1:]) for n, i in enumerate(todo, 1)]
    return "Subject: Please confirm a few details\n\nHello,\n\nI am looking into this: " + question.strip()[:200] + "\n\nCould you please confirm the following?\n\n" + "\n".join(lines) + "\n\nThank you.\n"

def analyze(question, template, sources, extractor=None, emit=noop, slots=None, origin=None, previous=None):
    t, slots = today(), slots or SCHEMAS[template]
    extractor = extractor or RuleExtractor()
    claims, dropped, cl = [], 0, clusters([s for s in sources if s["text"]])
    cy = SG.cycles(sources)          # which application cycle each page is about; pages behind the newest cycle count as outdated
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
                               display=show(sl["kind"], v), stale=s["stale"] or s["id"] in cy["drift"] or (sl["kind"] == "date" and v < t), drift=s["id"] in cy["drift"], undated=s["undated"],
                               neg=sl["kind"] in ("docs", "text") and negated(c["quote"]), cluster=cl[s["id"]], before=b, after=a))
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
                    q = next((x for x in s["text"].split("\n") if m.group(0).lower() in x.lower()), "").strip()
                    if len(q) > 300: j = q.lower().find(m.group(0).lower()); q = q[max(0, j - 100): j + 200].strip()
                    b, a = _ctx(s["text"], q)
                    hits.append(dict(slot=sl["id"], source_id=s["id"], source_name=s["name"], authority=s["authority"], quote=q, display="", stale=False,
                                     undated=s["undated"], neg=False, cluster=cl.get(s["id"]), before=b, after=a))
            read = len([s for s in sources if s["text"]])
            if not read: item.update(state="gap", summary="No readable page was provided, so this could not be checked.", searched=[])
            elif hits: item.update(state="check", summary="Related words appear but no clear statement was found. Read the quotes.", claims=hits[:2])
            else: item.update(state="gap", summary=f"Not found in the {read} page{'s' if read != 1 else ''} reviewed (searched for: {', '.join(repr(x) for x in sl['terms'][:3])}).", searched=sl["terms"][:3])
        elif ng and pos:
            item.update(state="conflict", claims=cs, summary=f"Wording differs: {names(pos)} state it, but {names(ng)} negate or relax it (see quotes).")
        elif ng:
            item.update(state="check", claims=cs, summary=f"Only negated or optional wording found in {names(ng)}. Read the quote.")
        elif len(distinct) > 1:
            top = _top(fresh)
            item.update(state="conflict", claims=cs, summary="Pages disagree: " + "; ".join(f"{c['source_name']} says {val(c)}" for c in fresh) + "."
                        + (f" Highest-authority source by domain heuristic: {top}; still verify." if top else ""))
        elif stale:
            old = "; ".join(f"{c['source_name']} says {val(c)}" for c in stale)
            now_ = f" The newer page(s) say {val(fresh[0])}." if fresh else " No current page confirms it."
            item.update(state="stale", claims=cs, summary=f"Possibly outdated: {old} (older page or past date).{now_}")
        elif len({c["cluster"] for c in fresh}) >= 2 and sl["kind"] == "text":
            item.update(state="check", claims=cs, summary=f"{names(fresh)} all mention this, but free-text wording cannot be compared by code. Read the quotes and check they agree.")
        elif len({c["cluster"] for c in fresh}) >= 2:
            item.update(state="confirmed", claims=cs, summary=f"Matches across {names(fresh)}: {val(fresh[0])}.")
        else:
            copied = len({c["source_id"] for c in fresh}) >= 2
            item.update(state="single", claims=cs, summary=(f"{names(fresh)} state it, but their text is mostly identical, so this is not independent confirmation: {val(fresh[0])}."
                        if copied else f"Only {fresh[0]['source_name']} covers this: {val(fresh[0])}."))
        if item["state"] in ("conflict", "single") and any(c["undated"] for c in item["claims"]): item["summary"] += " At least one page shows no date."
        cf, why = confidence(item["state"], item["claims"])
        item.update(chip=LABEL[item["state"]], rank=RANK[item["state"]], w=sl["w"], confidence=cf, confidence_why=why,
                    ask=ASK[item["state"]].format(l=sl["label"]))
        (confirmed if item["state"] == "confirmed" else items).append(item)
    items.sort(key=lambda x: (x["rank"], -x["w"]))
    n = len(items)
    unreadable = not any(s["text"] for s in sources)
    verdict = "Nothing could be checked: no page was readable." if unreadable else "Everything checked is confirmed across pages." if n == 0 else f"Not ready yet: {n} thing{'s' if n != 1 else ''} to verify"
    keys = ("id", "name", "url", "date", "date_method", "undated", "stale", "injection", "error", "truncated", "authority", "hash", "retrieved_at")
    src_out = [{**{k: (str(s[k]) if k == "date" and s[k] else s[k]) for k in keys if k in s}, "cycle": (cy["per"].get(s["id"]) or {}).get("label"), "cycle_drift": s["id"] in cy["drift"]} for s in sources]
    found = len([i for i in items + confirmed if i["state"] not in ("gap", "check")])
    allit = items + confirmed
    snap, ready = snapshot(allit, sources, t), readiness(allit)
    dups = [sorted(s["name"] for s in sources if cl.get(s["id"]) == r) for r in sorted({v for v in cl.values()}) if list(cl.values()).count(r) > 1]
    kind = {x["id"]: x["kind"] for x in slots}; by = {i["slot"]: i for i in items + confirmed}
    def cell(c, st):
        t = c["display"] if c["display"] and kind[c["slot"]] != "text" else c["quote"]
        flags = [f for f, on in (("no visible date", c["undated"]), ("older or past-dated", c["stale"] and not c.get("drift")), ("earlier application cycle", c.get("drift")), ("negated or optional wording", c["neg"]),
                                 ("related words only", st == "check" and not c["display"])) if on]
        return dict(text=t[:90] + ("…" if len(t) > 90 else ""), quote=c["quote"][:240], flags=flags)
    overview = dict(sources=[dict(id=s["id"], name=s["name"], authority=s["authority"]) for s in sources if s["text"]],
                    rows=[dict(slot=sl["id"], label=sl["label"], state=by[sl["id"]]["state"], chip=by[sl["id"]]["chip"],
                               cells={sid: [cell(c, by[sl["id"]]["state"]) for c in by[sl["id"]]["claims"] if c["source_id"] == sid]
                                      for sid in sorted({c["source_id"] for c in by[sl["id"]]["claims"]})}) for sl in slots])
    reviewed = len([s for s in sources if s["text"]])
    hed = SG.hedges(sources, slots)
    ready["path"] = SG.impact_path(allit, CREDIT, ready["pct"])
    for it in allit: it["caveats"] = [h for h in hed if h["slot"] == it["slot"]]
    qs = SG.questions(items, hed, reviewed, val)
    fp = SG.fingerprint(question, sources, allit)
    cyc = dict(newest=cy["newest"], drift=[dict(source_id=k, source_name=next(s["name"] for s in sources if s["id"] == k), **v) for k, v in cy["drift"].items()],
               unstated=[dict(source_id=k, source_name=next(s["name"] for s in sources if s["id"] == k)) for k in cy["unstated"]])
    indep = dict(pages=reviewed, independent=len({cl[s["id"]] for s in sources if s["text"]}), official=len([s for s in sources if s["text"] and s["authority"] == "official"]))
    for it in items + confirmed:
        for c in it["claims"]: c.pop("value", None); c.pop("cluster", None); c.pop("drift", None)
        it.pop("w", None)
    emit(6, "Building dashboard")
    return dict(question=question, template=template, today=str(t), extractor=extractor.name, checklist_origin=origin or "template:" + template,
                verdict=verdict, meter=dict(total=len(slots), found=found, corroborated=len(confirmed), to_verify=n),
                note="Findings are signals from rules or AI, not facts. “Not found” means not found in these pages, not that it doesn’t exist. "
                     "Source authority is guessed from the domain and can be wrong.",
                items=items, confirmed=confirmed, sources=src_out, dropped=dropped,
                readiness=ready, overview=overview, cycles=cyc, hedges=hed, questions=qs, independence=indep, fingerprint=fp, duplicates=dups, snapshot=snap, changes=diff(previous, snap) if previous else None, email_draft="" if unreadable else email_draft(question, items))
