"""v6 regression tests: overview table, reader fixes, server-decided authority, free-text confirmation."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["DARKSPOT_TODAY"] = "2026-10-31"
from darkspot import analyze as A, api, checklist as C, facts

def run(texts, q="What should I verify before applying for this scholarship?"):
    slots, _ = C.build(q)
    srcs = [A.make_source(i, n, None, t, False, A.today()) for i, (n, t) in enumerate(texts, 1)]
    return A.analyze(q, "auto", srcs, slots=slots), srcs

class V6(unittest.TestCase):
    def test_overview_matches_findings_and_quotes_are_verbatim(self):
        r = A.analyze("q", "scholarship", A.load_sources(sample=True)); o = r["overview"]
        self.assertEqual([x["slot"] for x in o["rows"]], ["eligibility", "deadline", "documents", "renewal", "link", "amount"])
        states = {i["slot"]: i["state"] for i in r["items"] + r["confirmed"]}
        self.assertEqual({x["slot"]: x["state"] for x in o["rows"]}, states)
        texts = {s["id"]: s["text"] for s in A.load_sources(sample=True)}
        for row in o["rows"]:
            for sid, cells in row["cells"].items():
                for c in cells: self.assertIn(c["quote"][:60], texts[sid])
    def test_gap_row_has_no_cells(self):
        row = next(x for x in A.analyze("q", "scholarship", A.load_sources(sample=True))["overview"]["rows"] if x["slot"] == "renewal")
        self.assertEqual(row["cells"], {})
    def test_final_date_is_a_deadline(self):
        r, _ = run([("P", "The final date was 20 January 2027.")])
        d = next(i for i in r["items"] + r["confirmed"] if i["slot"] == "deadline"); self.assertEqual(d["claims"][0]["display"], "20 Jan 2027")
    def test_later_negation_is_not_hidden_by_earlier_requirement(self):
        r, _ = run([("P", "You need a caste certificate and bank passbook. Nobody asked for an income certificate.")])
        d = next(i for i in r["items"] if i["slot"] == "documents"); self.assertEqual(d["state"], "conflict"); self.assertEqual(len(d["claims"]), 2)
    def test_free_text_agreement_is_not_called_confirmed(self):
        r, _ = run([("A", "Renewal is allowed every year if you keep 60% marks."), ("B", "Renewal is possible only for the top 10 students each year.")])
        i = next(x for x in r["items"] + r["confirmed"] if x["slot"] == "renewal"); self.assertEqual(i["state"], "check")
        self.assertIn("cannot be compared by code", i["summary"])
    def test_free_text_summary_shows_quote_not_the_word_stated(self):
        r, _ = run([("A", "Renewal is allowed every year if you keep 60% marks.")])
        i = next(x for x in r["items"] if x["slot"] == "renewal"); self.assertNotIn("stated", i["summary"]); self.assertIn("Renewal is allowed", i["summary"])
    def test_authority_cannot_be_upgraded_by_the_client(self):
        w = api.do_sources({"text": "Last date to apply: 1 December 2030.", "name": "x"})
        self.assertEqual(w["authority"], "pasted"); w["authority"] = "official"
        with self.assertRaises(api.ApiError): api.from_wire(w, 1)
        w2 = api.do_sources({"sample": 1, "idx": 1}); self.assertEqual(api.from_wire(w2, 1)["authority"], "official")
    def test_authority_cannot_be_forged_for_a_link_either(self):
        w = api.do_sources({"text": "Last date to apply: 1 December 2030.", "name": "x"}); w["url"] = "https://x.gov.in/a"
        with self.assertRaises(api.ApiError): api.from_wire(w, 1)

if __name__ == "__main__": unittest.main()
