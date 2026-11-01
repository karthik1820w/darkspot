"""Tiny labelled evaluation of the offline rule reader. Hand-written by the project author: optimistic, small, NOT a benchmark.
Each case: (text, template, slot, expected display value or None meaning 'must not report anything')."""
import os, sys
os.environ["DARKSPOT_TODAY"] = "2026-10-31"; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from darkspot import analyze as A
from darkspot.facts import RuleExtractor, SCHEMAS
D = "30 Nov 2026"
CASES = [  # ---- positives: a real deadline / fee / processing time phrased differently
 ("Applications close on 30 November 2026.", "scholarship", "deadline", D), ("Last date: 30 Nov 2026", "scholarship", "deadline", D),
 ("Deadline - November 30, 2026", "scholarship", "deadline", D), ("The due date for submission is 30-11-2026.", "scholarship", "deadline", D),
 ("Submit your form by 30 November 2026.", "scholarship", "deadline", D), ("Applications are accepted until 30 November 2026.", "scholarship", "deadline", D),
 ("Apply before 30 November 2026.", "scholarship", "deadline", D), ("The portal shuts on 30/11/2026.", "scholarship", "deadline", D),
 ("Forms must reach us no later than 30 November 2026.", "scholarship", "deadline", D), ("Registration costs $350 per applicant.", "general", "cost", "$350"),
 ("You will pay $350 at submission.", "general", "cost", "$350"), ("The price is €200.", "general", "cost", "€200"), ("A fee of Rs. 500 is payable online.", "general", "cost", "₹500"),
 ("Visa processing takes 4 weeks.", "visa", "processing", "28 days"), ("Decisions usually arrive within 3 weeks.", "visa", "processing", "21 days"),
 ("Expect an answer in about a month.", "visa", "processing", None),   # no number: correct behaviour is to report nothing
 # ---- negatives: dates and money that are NOT the thing asked about
 ("Published: 12 August 2026.", "scholarship", "deadline", None), ("The foundation was founded on 4 May 1998.", "scholarship", "deadline", None),
 ("Posted by admin on 3 October 2024.", "scholarship", "deadline", None), ("The award ceremony is held on 15 December 2026.", "scholarship", "deadline", None),
 ("Updated on 2 March 2026 with new photos.", "scholarship", "deadline", None), ("Our office is open Monday to Friday.", "scholarship", "deadline", None),
 ("Last year 5,000 students applied.", "general", "cost", None), ("Donate $10 to support our work.", "general", "cost", None),
]
def run():
    tp = fp = fn = tn = 0; rows = []
    for text, tpl, slot, exp in CASES:
        s = A.make_source(1, "t", None, text, False, A.today()); got = [c for c in RuleExtractor().extract(s, SCHEMAS[tpl]) if c["slot"] == slot]
        from darkspot.facts import normalise, show
        sl = next(x for x in SCHEMAS[tpl] if x["id"] == slot); g = show(sl["kind"], normalise(sl["kind"], got[0]["quote"])) if got else None
        ok = g == exp
        if exp is None: tn, fp = (tn + 1, fp) if g is None else (tn, fp + 1)
        elif g == exp: tp += 1
        elif g is None: fn += 1
        else: fp += 1; fn += 1
        if not ok: rows.append((text[:52], exp, g))
    pos = [c for c in CASES if c[3]]; print(f"cases: {len(CASES)}  correct: {tp + tn}  recall on {len(pos)} positives: {tp}/{len(pos)} = {tp/len(pos):.0%}  false reports: {fp}  correct silences: {tn}")
    for r in rows: print("   miss:", r)
    return tp, len(pos), fp
if __name__ == "__main__": run()
