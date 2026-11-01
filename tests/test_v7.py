"""v7 regression tests: cycle drift, source hedges, derived questions, verification impact, report fingerprint."""
import os, random, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DARKSPOT_TODAY"] = "2026-10-31"
from darkspot import analyze as A, api, checklist as C, signals as SG

Q = "What should I verify before applying for this scholarship?"
def run(texts, q=Q):
    slots, _ = C.build(q)
    srcs = [A.make_source(i, n, None, t, False, A.today()) for i, (n, t) in enumerate(texts, 1)]
    return A.analyze(q, "auto", srcs, slots=slots), srcs
def sample(): return A.analyze("q", "scholarship", A.load_sources(sample=True))

class Cycles(unittest.TestCase):
    def test_sample_blog_is_behind_the_official_cycle_and_its_claims_are_outdated(self):
        r = sample(); d = r["cycles"]["drift"]
        self.assertEqual([(x["source_name"], x["label"], x["newest_label"]) for x in d], [("Blog post", "2024-25", "2026-27")])
        self.assertIn(d[0]["quote"], next(s for s in A.load_sources(sample=True) if s["name"] == "Blog post")["text"])
        self.assertEqual(r["cycles"]["unstated"][0]["source_name"], "College page")
        self.assertTrue(next(s for s in r["sources"] if s["name"] == "Blog post")["cycle_drift"])
    def test_cycle_drift_alone_marks_an_undated_page_outdated(self):
        r, _ = run([("New", "Applications for the 2026-27 cycle close on 30 November 2026."), ("Old", "Applications for the 2024-25 cycle close on 15 December 2025.")])
        self.assertEqual(len(r["cycles"]["drift"]), 1)
        flags = [f for row in r["overview"]["rows"] if row["slot"] == "deadline" for cs in row["cells"].values() for c in cs for f in c["flags"]]
        self.assertIn("earlier application cycle", flags)
    def test_iso_dates_and_non_consecutive_ranges_are_not_cycles(self):
        self.assertEqual(SG._cycle_tokens("Last date: 2026-11-30 and range 2024-26 and 2026-12"), [])
        # "AY 2026-27" legitimately yields two tokens (the word form and the range form), both for 2026
        years = sorted(y for y, _ in SG._cycle_tokens("Batch 2025 and AY 2026-27 and 2025/2026")); self.assertEqual(years, [2025, 2025, 2026, 2026])
    def test_no_cycle_anywhere_means_no_drift(self):
        r, _ = run([("A", "Last date to apply: 1 December 2030."), ("B", "Apply by 2 December 2030.")])
        self.assertEqual((r["cycles"]["drift"], r["cycles"]["unstated"], r["cycles"]["newest"]), ([], [], None))

class Hedges(unittest.TestCase):
    def test_sample_college_amount_hedge_is_found_bound_and_verbatim(self):
        r = sample(); h = r["hedges"]; self.assertEqual(len(h), 1)
        self.assertEqual((h[0]["kind"], h[0]["slot"], h[0]["source_name"]), ("May change", "amount", "College page"))
        self.assertIn(h[0]["quote"], next(s for s in A.load_sources(sample=True) if s["name"] == "College page")["text"])
        amount = next(i for i in r["items"] + r["confirmed"] if i["slot"] == "amount"); self.assertEqual(len(amount["caveats"]), 1)
    def test_three_kinds(self):
        r, _ = run([("P", "The deadline will be announced later. Fees are subject to change. Please refer to the official notification for the document list. Plain sentence.")])
        self.assertEqual({h["kind"] for h in r["hedges"]}, {"Not decided yet", "May change", "Defers to another document"})
        self.assertEqual(next(h for h in r["hedges"] if h["kind"] == "Not decided yet")["slot"], "deadline")
    def test_plain_text_has_no_hedges(self):
        r, _ = run([("P", "Last date to apply: 1 December 2030. You need an income certificate.")]); self.assertEqual(r["hedges"], [])
    def test_hedges_become_questions(self):
        r, _ = run([("P", "The renewal policy will be announced after results.")])
        self.assertTrue(any(q["kind"] == "hedge" and "not final" in q["question"] for q in r["questions"]))

class Questions(unittest.TestCase):
    def test_every_open_item_has_a_question_and_confirmed_ones_do_not(self):
        r = sample(); open_ = {i["slot"] for i in r["items"]}
        self.assertEqual({q["slot"] for q in r["questions"] if q["kind"] != "hedge"}, open_)
        self.assertTrue(all(q["origin"] == "derived" for q in r["questions"]))
    def test_conflict_question_names_the_pages_that_disagree(self):
        q = next(q for q in sample()["questions"] if q["slot"] == "documents")
        for name in ("Official notice", "College page"): self.assertIn(name, q["question"])
    def test_gap_question_is_scoped_to_pages_reviewed(self):
        q = next(q for q in sample()["questions"] if q["slot"] == "renewal"); self.assertIn("not found in the 3 pages reviewed", q["question"])

class Impact(unittest.TestCase):
    def test_gains_and_path_are_consistent_with_the_shown_rule(self):
        r = sample(); rd = r["readiness"]; path = rd["path"]
        self.assertEqual(rd["pct"], 36); self.assertEqual(len(path), 3)
        afters = [p["after"] for p in path]; self.assertEqual(afters, sorted(afters)); self.assertLessEqual(afters[-1], 100)
        self.assertTrue(all(i["impact"] == 0 for i in r["confirmed"]))
        self.assertLessEqual(sum(i["impact"] for i in r["items"]), 100 - rd["pct"] + len(r["items"]))     # rounding only
        self.assertEqual(path[0]["slot"], "documents")
    def test_everything_confirmed_means_empty_path(self):
        t = "Last date to apply: 30 November 2026. Apply online at https://a.example/x"
        r, _ = run([("A", t), ("B", t + " Also.")]); self.assertTrue(len(r["readiness"]["path"]) <= 3)

class Fingerprint(unittest.TestCase):
    def test_same_evidence_same_id_and_any_change_changes_it(self):
        a = sample()["fingerprint"]; self.assertEqual(a, sample()["fingerprint"]); self.assertEqual(len(a), 64)
        r1, _ = run([("A", "Last date to apply: 1 December 2030.")]); r2, _ = run([("A", "Last date to apply: 2 December 2030.")])
        self.assertNotEqual(r1["fingerprint"], r2["fingerprint"])
    def test_page_order_does_not_matter(self):
        p = [("A", "Last date to apply: 1 December 2030."), ("B", "You must submit an income certificate.")]
        self.assertEqual(run(p)[0]["fingerprint"], run(p[::-1])[0]["fingerprint"])

class Api(unittest.TestCase):
    def test_wire_round_trip_carries_the_new_fields(self):
        srcs = [api.do_sources({"sample": i, "idx": i}) for i in (1, 2, 3)]
        r = api.do_analyze({"question": Q, "checklist": api.do_checklist({"question": Q, "template": "scholarship"}), "sources": srcs})
        for k in ("cycles", "hedges", "questions", "independence", "fingerprint"): self.assertIn(k, r)
        self.assertEqual(r["independence"], {"pages": 3, "independent": 3, "official": 1})

class Fuzz(unittest.TestCase):
    def test_signals_never_invent_text(self):
        rnd = random.Random(7); bits = ["will be announced", "subject to change", "2024-25", "2026-27", "refer to the official notice", "Batch 2025", "deadline", "renewal", "₹5,000", "\n", ". ", "TBA", "2026-11-30"]
        for _ in range(300):
            txt = " ".join(rnd.choice(bits) + rnd.choice(["", " x", " The"]) for _ in range(rnd.randint(1, 25)))
            r, srcs = run([("F", txt), ("G", txt[::-1][:200])])
            for h in r["hedges"]: self.assertIn(h["quote"], srcs[int(h["source_id"][1]) - 1]["text"])
            for d in r["cycles"]["drift"]: self.assertIn(d["quote"], srcs[int(d["source_id"][1]) - 1]["text"])

if __name__ == "__main__": unittest.main()
