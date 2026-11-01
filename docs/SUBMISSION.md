# Submission text (paste into Unista)

## Project name
DarkSpot: AI-Assisted Information Gap Detection

## Project description
**Problem.** People decide on scholarships, visas and courses using pages that are scattered, outdated or contradictory. Search finds pages and summarisers condense them, but neither tells you what is missing or what to check before you act.

**Solution.** DarkSpot takes a question and the sources the user found (links, pasted text, PDFs) and returns a prioritised verification checklist: conflicts between sources, items not covered, outdated or undated details, and items backed by only one page. Every finding shows the exact quote behind it.

**How it works.** (1) The question selects an expected-answer checklist (scholarship, visa, general; an optional Claude-generated checklist is validated and off by default). (2) Sources are collected in parallel, cleaned, dated and tagged with an authority guess from the domain, and hashed. (3) A reader finds candidate quotes. (4) Code, not AI, verifies each quote appears verbatim in the stored page text and derives the value from it. (5) Pages are compared: conflicts, negated wording, stale dates, gaps (always scoped to "not found in the N pages reviewed"). (6) The dashboard separates Sourced (quote), Derived (decided by code) and Suggested (not from sources) content.

**Major features.** A "What the sources say" table (every expected item against every page, each cell with its own quote); conflict view with both quotes side by side; gap and outdated-date warnings; prioritised checklist; decision-readiness score with its rule shown; confidence labels with reasons; copy detection (a page that copies another is not independent confirmation); change detection (re-run later and see what changed); evidence receipts (sha256 and read time) and downloadable evidence; ready-to-send email to the provider listing only open items; PDF upload; live progress; light/dark, mobile and keyboard-accessible UI.

**New in v7 (innovation).** (a) Application-cycle drift: a page about 2024-25 beside a 2026-27 notice is treated as outdated even with no visible date. (b) The source admits it: "subject to change", "will be announced" and "refer to the official notification" sentences are quoted and attached to the affected item. (c) Open questions written by code from the findings, answering the brief's "unanswered questions". (d) Verification path: each open item shows the readiness points it is worth and the shortest route to a ready decision (a what-if on the disclosed rule). (e) A tamper-evident report ID over the question, page hashes and findings.

**Uniqueness.** The product is the gap analysis, not a summary: no claim exists without a verbatim quote, absence is scoped, negation ("you do not need X") is treated as a conflict instead of a confirmation, and copies do not count as corroboration. AI output is labelled as a signal, never as fact.

**Technology.** Python (no framework) serverless API on Vercel, vanilla JavaScript front end with a strict Content-Security-Policy, an offline rule-based reader by default (no AI needed to run the core workflow), an optional Claude reader that is off unless a key is configured, optional HMAC-signed evidence, pypdf. Security: SSRF protection with IP pinning and per-redirect checks, size and time limits, text-only rendering, injection flagging. Quality: 71 unit/integration tests, 21 backend, 10 fuzz and 17 browser system probes, regression tests for every defect found, and a small labelled evaluation.

**Future scope.** More topic checklists, a held-out accuracy benchmark on real pages, semantic conflict detection for free-text answers (still gated by the verbatim-quote check), browser extension, shared reports, multilingual sources.

**Limits (stated in the app too).** Findings are signals, not facts. The offline reader is keyword-based; the Claude reader and search discovery are optional and were not evaluated at scale. Authority is guessed from the domain.

## 90-second demo script (matches the suggested flow in the problem statement)
1. (0:00) Landing page: one sentence on the problem. Click "Scholarship" example, then "See it in 10 seconds".
2. (0:10) Show the checklist "What I will look for" and the live progress steps.
3. (0:20) Dashboard: readiness 36%, tally chips, then the "What the sources say" table (what each page states, quote under every value, "Not found" cells), and the Sourced / Derived / Suggested key.
4. (0:30) Open "Required documents": two sources list different documents, quotes side by side, authority badges.
4b. (0:40) Point at the "Fastest route" line (36% to 91%), the "Earlier application cycle detected" box (blog 2024-25 vs official 2026-27), the open questions, and the college page's "subject to change" hedge.
5. (0:45) "Renewal conditions": Missing, scoped to the pages reviewed. "Deadline": outdated blog page.
6. (0:55) Show a copy-detection or negation example (paste the two lines from the README).
7. (1:05) Draft email to provider; Download evidence (hashes).
8. (1:15) Re-run to show "changed since your last check". Close on the limits line.
