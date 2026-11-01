# Scorecard against the Shinchan Online Hackathon 2026 judging criteria

Builder's own estimate, using the official weights (total 10). Judges decide; this is not a prediction of their marks.

| Evaluation area | Weight | Max | Score | Evidence in this repo | What holds it back |
|---|---|---|---|---|---|
| Problem understanding and relevance | 15% | 1.5 | **1.3** | Exact brief scenario (scholarship), visa and general templates, honest scoping of "missing" | Three fixed templates; no user research |
| Innovation and originality | 20% | 2.0 | **1.8** | Verbatim-quote gate, negation as conflict, copy detection, change detection, **cycle drift, self-admitted hedges, derived open questions, verification path, report ID** (v7), each tested | Rules, not learned semantics; some ideas echo fact-checking research |
| Working prototype and functionality | 25% | 2.5 | **2.2** | Whole flow works offline: input, sources, findings, checklist, email, exports; 71 + 48 automated checks | Not deployed; keyword reader misses paraphrases (14/15 on a tuned set) |
| Technical implementation | 15% | 1.5 | **1.3** | Stdlib stack, SSRF pinning, CSP, HMAC evidence, stateless API, regression tests for 13 defects | Vercel, Claude reader and real-internet fetching untested here |
| Evidence, accuracy and transparency | 15% | 1.5 | **1.4** | Every finding has a verbatim quote; absence scoped; Sourced/Derived/Suggested lanes; hashes | Confidence and readiness are uncalibrated heuristics |
| Presentation and demo | 10% | 1.0 | **0.8** | 10-slide deck, narrated demo video, script | Synthetic voice; no live Q&A yet |
| **Total** | 100% | 10 | **8.8** | Estimated range 8.3 to 9.1 | |

Innovation moved from an estimated 1.5 (v6) to 1.8 (v7) because five additional mechanisms are implemented, tested and demonstrable in the 10-second sample run. The remaining 0.2 would need a held-out accuracy benchmark on real pages and semantic (not keyword) conflict detection.
