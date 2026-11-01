"""Slot schemas, value normalisers, rule-based quote finder, verifier, negation guard.
Extractors (rules, Claude) only FIND QUOTES. Values are re-derived from the quote by code."""
import re
from datetime import date

_M = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
MON = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
D3 = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?!\d)")
D1 = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_M},?\s+(\d{{4}})\b", re.I)
D2 = re.compile(rf"\b{_M}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)
D4 = re.compile(r"(?<![\d/.-])(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")

def _mk(y, m, d):
    try: return date(int(y), int(m), int(d))
    except ValueError: return None

def _numeric(a, b, y):
    """dd/mm/yyyy vs mm/dd/yyyy. Ambiguous (both <= 12, different) is NOT guessed: returns None."""
    a, b = int(a), int(b)
    if a > 12 and b <= 12: return _mk(y, b, a)
    if b > 12 and a <= 12: return _mk(y, a, b)
    if a == b: return _mk(y, a, b)
    return None

def parse_dates(s):
    out = [_mk(*m.groups()) for m in D3.finditer(s)]
    out += [_mk(m.group(3), MON[m.group(2).lower()], m.group(1)) for m in D1.finditer(s)]
    out += [_mk(m.group(3), MON[m.group(1).lower()], m.group(2)) for m in D2.finditer(s)]
    out += [_numeric(*m.groups()) for m in D4.finditer(s)]
    return [d for d in out if d]

CUR = {"₹": "₹", "rs": "₹", "inr": "₹", "$": "$", "usd": "$", "€": "€", "eur": "€", "£": "£", "gbp": "£"}
AMT = re.compile(r"(₹|rs\.?|inr|\$|usd|€|eur|£|gbp)\s?([\d,]+(?:\.\d+)?)", re.I)
DUR = re.compile(r"(\d+)(?:\s*(?:-|–|to)\s*(\d+))?\s*(business |working )?(day|week|month)s?\b", re.I)
URL = re.compile(r"https?://[^\s)>\]]+")
DOCS = {"income certificate": r"income (certificate|proof)", "marksheet": r"mark ?sheet|marks? card|transcript",
        "photo ID": r"photo ?id|id proof|identity (card|proof)|aadhaar", "bank passbook": r"passbook|bank (statement|details)",
        "caste certificate": r"caste certificate"}
NEG = re.compile(r"\b(?:not|never|no longer|no need|nobody|no one|none|without|optional|waived?|exempt\w*)\b|n['’]t\b", re.I)

def negated(q):
    """Quote contains negation or relaxing words. Signal only, shown to the user."""
    return bool(NEG.search(q))

def normalise(kind, q):
    """Value derived from the quote itself; None means 'cannot support this claim'."""
    if kind == "money":
        v = set()
        for c, n in AMT.findall(q):
            n = float(n.replace(",", "").rstrip(".") or "nan") if n.strip(",.") else None
            if n is not None: v.add((CUR[c.lower().rstrip(".")], int(n) if n == int(n) else n))
        return tuple(sorted(v)) or None
    if kind == "duration":
        mult = {"day": 1, "week": 7, "month": 30}
        v = {int(x) * mult[m.group(4).lower()] for m in DUR.finditer(q) for x in (m.group(1), m.group(2)) if x}
        return tuple(sorted(v)) or None
    if kind == "date":
        d = parse_dates(q); return d[0] if d else None
    if kind == "docs":
        v = frozenset(k for k, p in DOCS.items() if re.search(p, q, re.I)); return v or None
    if kind == "url":
        m = URL.search(q); return m.group(0).rstrip(".,;") if m else None
    return "stated" if q.strip() else None

def show(kind, v):
    if kind == "money": return " / ".join(f"{c}{n:,}" for c, n in v)
    if kind == "duration": return " / ".join(f"{d} days" for d in v)
    if kind == "date": return f"{v.day} {v.strftime('%b %Y')}"
    if kind == "docs": return ", ".join(sorted(v))
    return "stated" if kind == "text" else str(v)

KINDS = ("money", "date", "duration", "docs", "url", "text")

def slot(id, label, kind, terms, verify, w=3, find=None):
    f = find or "|".join(re.escape(t) for t in terms)
    return dict(id=id, label=label, w=w, kind=kind, find=re.compile(f, re.I), terms=list(terms), verify=verify)

SCHEMAS = {
    "scholarship": [
        slot("eligibility", "Eligibility", "money", ["eligib", "income", "criteria"], "Check the eligibility rules on the official notice.", 3,
             r"eligib|family income|income (limit|below|under|cap)"),
        slot("deadline", "Deadline", "date", ["deadline", "last date", "apply by", "closes"], "Confirm the current deadline on the latest official notice.", 5,
             r"deadline|last date|apply by|closes?\b|due date|until|before|shuts?\b|no later than|final date|last day|(?:submit\w*|reach\w*)(?:\s+\w+){0,4}\s+by"),
        slot("documents", "Required documents", "docs", ["document", "certificate", "marksheet", "submit"], "Check the document list on the official notice.", 5,
             r"submit|bring|documents?|certificate|marksheet|passbook"),
        slot("renewal", "Renewal conditions", "text", ["renew", "continuation", "next year", "reapply", "re-apply", "following year", "every year"],
             "Look for renewal rules on the official site, or ask the foundation.", 4, r"renew|continuation|next year|re-?apply"),
        slot("link", "Application link", "url", ["http", "portal", "apply online", "application form"],
             "Open the application link from the official site, not from a copy.", 4, r"https?://|application (link|portal)|apply online"),
        slot("amount", "Award amount", "money", ["amount", "award", "stipend", "worth"], "Confirm the amount on the official notice.", 2,
             r"amount|award|stipend|worth")],
    "visa": [
        slot("processing", "Processing time", "duration", ["processing", "takes", "weeks", "days"], "Confirm current processing time on the official immigration site.", 4,
             r"process|takes?|weeks?|days?"),
        slot("fee", "Fee", "money", ["fee", "cost", "charge", "pay"], "Confirm the fee on the official fee schedule.", 5, r"\bfees?\b|cost|charge|pay"),
        slot("documents", "Required documents", "text", ["document", "passport", "submit", "bring"], "Check the official document checklist.", 5,
             r"documents?|passport|submit|bring|certificate"),
        slot("eligibility", "Eligibility", "text", ["eligib", "must", "requirement"], "Check eligibility rules for your nationality and course.", 4, r"eligib|requirement|must have"),
        slot("keydate", "Key dates and validity", "date", ["deadline", "valid", "expires", "appointment"], "Confirm dates on the official site.", 3,
             r"deadline|last date|valid|expires?|appointment"),
        slot("link", "Application link", "url", ["http", "portal", "apply online"], "Use the link from the official site.", 3, r"https?://|portal|apply online")],
    "general": [
        slot("deadline", "Deadline or key date", "date", ["deadline", "last date", "apply by", "closes"], "Confirm dates with the official source.", 5,
             r"deadline|last date|apply by|closes?\b|due date|until|before|shuts?\b|no later than|final date|last day|(?:submit\w*|reach\w*)(?:\s+\w+){0,4}\s+by"),
        slot("cost", "Cost or fee", "money", ["fee", "cost", "price", "charge"], "Confirm costs with the official source.", 4, r"\bfees?\b|cost|price|charge|\bpay"),
        slot("eligibility", "Eligibility", "text", ["eligib", "requirement", "must"], "Check who qualifies.", 4, r"eligib|requirement|must have"),
        slot("process", "How to apply", "text", ["apply", "process", "procedure", "steps"], "Find the official application steps.", 3, r"how to|steps?|procedure|apply"),
        slot("link", "Official link", "url", ["http", "portal", "website"], "Use the link from the official site.", 3, r"https?://|portal"),
        slot("contact", "Contact", "text", ["contact", "email", "phone", "helpline"], "Note a contact who can confirm details.", 2, r"contact|e-?mail|phone|helpline")],
}

def _chunks(p, n=300):
    """Very long runs (no sentence breaks) are cut at spaces so a quote never becomes a whole page."""
    while len(p) > n:
        cut = p.rfind(" ", 0, n); cut = cut if cut > 0 else n
        yield p[:cut].strip(); p = p[cut:].strip()
    if p: yield p

def sentences(text):
    for line in text.split("\n"):
        for p in re.split(r"(?<=[.!?])\s+(?=[A-Z₹$€£\"“])", line):
            yield from _chunks(p.strip())

class RuleExtractor:
    """Offline, deterministic: first sentence in each source that matches the slot pattern, plus the first negated one for text/docs slots."""
    name = "rules"
    def extract(self, src, slots):
        out, seen = [], set()
        for s in sentences(src["text"]):
            for sl in slots:
                if not sl["find"].search(s) or normalise(sl["kind"], s) is None: continue
                if sl["id"] not in seen: seen.add(sl["id"]); out.append({"slot": sl["id"], "quote": s})
                elif sl["kind"] in ("docs", "text") and negated(s) and not any(o["slot"] == sl["id"] and negated(o["quote"]) for o in out):
                    out.append({"slot": sl["id"], "quote": s})      # a later "you do NOT need X" must not be hidden by an earlier "you need Y"
        return out

def verify(claim, kind, text):
    """Quote must exist verbatim in the stored source text and support a value."""
    return claim["quote"] in text and normalise(kind, claim["quote"]) is not None
