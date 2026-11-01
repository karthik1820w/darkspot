"""Stage 2: expected-answer checklist. Offline: topic keywords pick a template. Live: Claude proposes items,
which are validated and capped here (model output is never trusted blindly) and fall back to rules on any failure."""
import re
from .facts import SCHEMAS, KINDS, slot

TOPICS = [("scholarship", r"scholar|stipend|fellowship|\bgrant\b"), ("visa", r"visa|immigra|passport|residence permit")]

def detect(q):
    return next((t for t, p in TOPICS if re.search(p, q, re.I)), "general")

def clean(items, limit=8):
    """Validate model-proposed items. Returns slots (possibly empty)."""
    out, seen = [], set()
    for it in items if isinstance(items, list) else []:
        try:
            id_, label, kind = str(it["id"]), str(it["label"])[:40], str(it["kind"])
            terms = [str(t).lower()[:30] for t in it["terms"] if str(t).strip()][:6]
            if not re.fullmatch(r"[a-z_]{2,24}", id_) or id_ in seen or not terms: continue
            if kind not in KINDS: continue
            kind = "text" if kind == "docs" else kind   # the docs vocabulary is scholarship-specific
            out.append(slot(id_, label, kind, terms, str(it.get("verify", "Confirm with the official source."))[:140], 3))
            seen.add(id_)
        except (KeyError, TypeError): continue
        if len(out) >= limit: break
    return out

def build(question, template="auto", llm=None):
    """Returns (slots, origin). origin is shown to the user so AI-suggested items are labelled."""
    if template in SCHEMAS: return SCHEMAS[template], "template:" + template
    if llm and hasattr(llm, "propose"):
        try:
            s = clean(llm.propose(question))
            if len(s) >= 3: return s, "claude (AI-suggested)"
        except Exception: pass
    t = detect(question)
    return SCHEMAS[t], "rules:" + t
