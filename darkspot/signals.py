"""v7 signals that go beyond search or summary. Everything here is deterministic, offline, and quote-backed:
  cycles()       which application cycle each page is about; pages stuck on an earlier cycle are flagged
  hedges()       sentences where a source itself admits it is incomplete ("will be announced", "subject to change", "refer to ...")
  questions()    the concrete questions the sources leave unanswered, built from the findings
  impact_path()  what-if readiness: how much each open item is worth, and the shortest path to a ready decision
  fingerprint()  tamper-evident report id over the question, page hashes and every finding
All outputs are signals for a human to check, never facts. Quotes are always verbatim substrings of the stored page text."""
import hashlib, json, re
from .facts import sentences

# ---- 1. application-cycle drift ---------------------------------------------------------------------------------------
PAIR = re.compile(r"(?<![\d/.-])(20\d{2})\s*[-–/]\s*(\d{4}|\d{2})(?![\d-])")
WORD = re.compile(r"\b(?:cycle|batch|intake|session|academic year|AY|edition|admissions?)\s+(?:of\s+|for\s+)?(20\d{2})(?!\d)", re.I)

def _cycle_tokens(sentence):
    """(start_year, label) pairs. A 'YYYY-YY' token only counts when the second part really is the next year, so ISO dates never match."""
    out = []
    for m in PAIR.finditer(sentence):
        a, b = int(m.group(1)), int(m.group(2))
        if (b % 100) == (a + 1) % 100: out.append((a, m.group(0)))
    out += [(int(m.group(1)), m.group(0)) for m in WORD.finditer(sentence)]
    return out

def cycles(sources):
    """Per readable source: the latest cycle it mentions, with the verbatim sentence. Then which pages sit behind the newest cycle seen."""
    per = {}
    for s in sources:
        if s.get("error") or not s.get("text"): continue
        best = None
        for sent in sentences(s["text"]):
            for yr, label in _cycle_tokens(sent):
                if best is None or yr > best["year"]: best = dict(year=yr, label=label, quote=sent)
        per[s["id"]] = best
    years = [v["year"] for v in per.values() if v]
    newest = max(years) if years else None
    ref = next((sid for sid, v in per.items() if v and v["year"] == newest), None)
    drift = {}
    if newest is not None:
        for sid, v in per.items():
            if v and v["year"] < newest:
                drift[sid] = dict(label=v["label"], quote=v["quote"], newest_label=per[ref]["label"], newest_source=ref)
    unstated = [sid for sid, v in per.items() if v is None] if newest is not None else []
    return dict(per=per, drift=drift, unstated=unstated, newest=newest)

# ---- 2. the source admits it ------------------------------------------------------------------------------------------
HEDGES = [
    ("Not decided yet", re.compile(r"\b(?:will|shall|to|yet to) be (?:announced|decided|notified|confirmed|declared|published|released|intimated)\b|\bTB[AD]\b|\bcoming soon\b|\bdetails (?:will )?follow\b", re.I)),
    ("May change", re.compile(r"\bsubject to (?:change|revision|approval|availability)\b|\bmay (?:vary|change)\b|\bat the discretion of\b|\bwithout (?:prior )?notice\b", re.I)),
    ("Defers to another document", re.compile(r"\b(?:please )?(?:refer to|see|consult|check) (?:the )?(?:official |latest |full |detailed |current )*(?:notification|notice|brochure|guidelines|website|portal|prospectus|terms)\b"
                                              r"|\bas per (?:the )?(?:latest |official |current )*(?:guidelines|norms|rules|notification|policy|regulations)\b|\bterms and conditions apply\b", re.I)),
]

def hedges(sources, slots, per_source=4):
    """Sentences where the page itself says the answer is not final or lives elsewhere. Bound to a checklist item when the sentence names it."""
    out = []
    for s in sources:
        if s.get("error") or not s.get("text"): continue
        n = 0
        for sent in sentences(s["text"]):
            kind = next((k for k, rx in HEDGES if rx.search(sent)), None)
            if not kind or sent not in s["text"]: continue
            low = sent.lower()
            slot = next((sl for sl in slots if any(t in low for t in sl["terms"])), None)
            out.append(dict(source_id=s["id"], source_name=s["name"], authority=s["authority"], kind=kind, quote=sent[:300],
                            slot=slot["id"] if slot else None, label=slot["label"] if slot else None))
            n += 1
            if n >= per_source: break
    return out

# ---- 3. what the sources leave unanswered -----------------------------------------------------------------------------
def questions(items, hedge_list, reviewed, val):
    """Concrete open questions, written from the findings by code. `val` renders a claim's value (passed in to avoid a circular import)."""
    qs = []
    for it in items:
        st, lab, cs = it["state"], it["label"], it["claims"]
        if st == "gap": q = f"What is the rule for “{lab}”? It was not found in the {reviewed} page{'s' if reviewed != 1 else ''} reviewed."
        elif st == "conflict":
            seen, parts = set(), []
            for c in cs:
                k = (c["source_id"], c["quote"])
                if k in seen: continue
                seen.add(k); parts.append(f"{c['source_name']} says {val(c)}")
            q = f"Which is current for “{lab}”? " + "; ".join(parts[:3]) + "."
        elif st == "stale": q = f"Is the older “{lab}” information still valid for the current cycle?"
        elif st == "check": q = f"Do the pages actually agree on “{lab}”? Read the highlighted lines and compare."
        elif st == "single": q = f"Can “{lab}” be confirmed by a second, independent page?"
        else: continue
        qs.append(dict(kind=st, slot=it["slot"], question=q, refs=sorted({c["source_id"] for c in cs}), origin="derived"))
    for h in hedge_list[:3]:
        qs.append(dict(kind="hedge", slot=h["slot"], question=f"{h['source_name']} says this is not final: “{h['quote'][:110]}{'…' if len(h['quote']) > 110 else ''}” What is the current answer?",
                       refs=[h["source_id"]], origin="derived"))
    return qs

# ---- 4. verification impact (what-if readiness) -----------------------------------------------------------------------
def impact_path(items, credit, pct, top=3):
    """items carry `w` and `state`. Gain = readiness points added if that item became fully confirmed. Pure arithmetic on the shown rule."""
    tot = sum(i["w"] for i in items) or 1
    for i in items: i["impact"] = round(100 * i["w"] * (1 - credit[i["state"]]) / tot)
    open_ = sorted((i for i in items if i["state"] != "confirmed"), key=lambda i: (-i["w"] * (1 - credit[i["state"]]), i["label"]))[:top]
    path, run = [], float(pct)
    exact = {i["slot"]: 100 * i["w"] * (1 - credit[i["state"]]) / tot for i in open_}
    for i in open_:
        run = min(100.0, run + exact[i["slot"]])
        path.append(dict(slot=i["slot"], label=i["label"], gain=i["impact"], after=round(run)))
    return path

# ---- 5. tamper-evident report id --------------------------------------------------------------------------------------
def fingerprint(question, sources, items):
    """sha256 over the question, every page hash and every finding with its quotes. Change a page or a finding and the id changes.
    Times and the order pages were added are excluded, so the same evidence always gives the same id."""
    body = dict(q=" ".join(question.split()).lower(), pages=sorted(s["hash"] for s in sources if s.get("hash")),
                findings=sorted((i["slot"], i["state"], sorted(c["quote"] for c in i["claims"])) for i in items))
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
