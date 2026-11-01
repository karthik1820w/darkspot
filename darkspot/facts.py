"""Slot schemas, value normalisers, rule-based quote finder, and the verifier.
Both extractors (rules, Claude) only FIND QUOTES. Values are re-derived from the quote by code."""
import re
from datetime import date

_M = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
MON = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
D3 = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?!\d)")
D1 = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_M},?\s+(\d{{4}})\b", re.I)
D2 = re.compile(rf"\b{_M}\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.I)

def _mk(y, m, d):
    try: return date(int(y), int(m), int(d))
    except ValueError: return None

def parse_dates(s):
    out = [_mk(*m.groups()) for m in D3.finditer(s)]
    out += [_mk(m.group(3), MON[m.group(2).lower()], m.group(1)) for m in D1.finditer(s)]
    out += [_mk(m.group(3), MON[m.group(1).lower()], m.group(2)) for m in D2.finditer(s)]
    return [d for d in out if d]

AMT = re.compile(r"(?:₹|rs\.?|inr)\s?([\d,]+(?:\.\d+)?)", re.I)
URL = re.compile(r"https?://[^\s)>\]]+")
DOCS = {"income certificate": r"income (certificate|proof)", "marksheet": r"mark ?sheet|marks? card|transcript",
        "photo ID": r"photo ?id|id proof|identity (card|proof)|aadhaar", "bank passbook": r"passbook|bank (statement|details)",
        "caste certificate": r"caste certificate"}

def normalise(kind, q):
    """Value derived from the quote itself; None means 'cannot support this claim'."""
    if kind == "money":
        v = {int(float(x.replace(",", "").rstrip("."))) for x in AMT.findall(q) if x.strip(",.")}
        return tuple(sorted(v)) or None
    if kind == "date":
        d = parse_dates(q); return d[0] if d else None
    if kind == "docs":
        v = frozenset(k for k, p in DOCS.items() if re.search(p, q, re.I)); return v or None
    if kind == "url":
        m = URL.search(q); return m.group(0).rstrip(".,;") if m else None
    return q.strip() or None

def show(kind, v):
    if kind == "money": return " / ".join(f"₹{n:,}" for n in v)
    if kind == "date": return f"{v.day} {v.strftime('%b %Y')}"
    if kind == "docs": return ", ".join(sorted(v))
    return "stated" if kind == "text" else str(v)

def _slot(id, label, w, kind, find, terms, verify):
    return dict(id=id, label=label, w=w, kind=kind, find=re.compile(find, re.I), terms=terms, verify=verify)

SCHEMAS = {"scholarship": [
    _slot("eligibility", "Eligibility", 3, "money", r"eligib|family income|income (limit|below|under|cap)",
          ["eligib", "income", "criteria"], "Check the eligibility rules on the official notice."),
    _slot("deadline", "Deadline", 5, "date", r"deadline|last date|apply by|closes?\b|due date",
          ["deadline", "last date", "apply by", "closes"], "Confirm the current deadline on the latest official notice."),
    _slot("documents", "Required documents", 5, "docs", r"submit|bring|documents?|certificate|marksheet|passbook",
          ["document", "certificate", "marksheet", "submit"], "Check the document list on the official notice."),
    _slot("renewal", "Renewal conditions", 4, "text", r"renew|continuation|next year|re-?apply",
          ["renew", "continuation", "next year", "reapply", "re-apply", "following year", "every year"],
          "Look for renewal rules on the official site, or ask the foundation."),
    _slot("link", "Application link", 4, "url", r"https?://|application (link|portal)|apply online",
          ["http", "portal", "apply online", "application form"], "Open the application link from the official site, not from a copy."),
    _slot("amount", "Award amount", 2, "money", r"amount|award|stipend|worth",
          ["amount", "award", "stipend", "worth"], "Confirm the amount on the official notice."),
]}

def sentences(text):
    for line in text.split("\n"):
        for p in re.split(r"(?<=[.!?])\s+(?=[A-Z₹\"“])", line):
            if p.strip(): yield p.strip()

class RuleExtractor:
    """Offline, deterministic: first sentence in each source that matches the slot pattern."""
    name = "rules"
    def extract(self, src, slots):
        out, seen = [], set()
        for s in sentences(src["text"]):
            for sl in slots:
                if sl["id"] not in seen and sl["find"].search(s) and normalise(sl["kind"], s) is not None:
                    seen.add(sl["id"]); out.append({"slot": sl["id"], "quote": s})
        return out

def verify(claim, kind, text):
    """Quote must exist verbatim in the stored source text and support a value."""
    return claim["quote"] in text and normalise(kind, claim["quote"]) is not None
