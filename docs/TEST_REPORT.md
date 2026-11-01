# Test report (v3 -> v4 adversarial testing; v6 addendum at the end)

Method: read the code for risky assumptions, wrote probes to prove or disprove each, fixed what failed, turned every finding into a permanent
regression test, then checked the tests themselves by mutation. All numbers below were produced in the build sandbox (no internet, no Vercel, no API keys).

## Defects found and fixed (13)
| ID | Sev | What went wrong | Fix | Regression test |
|----|-----|-----------------|-----|-----------------|
| F07 | High | A page with no sentence breaks produced a 280,000-character "quote" (breaks the UI and Vercel's response limit) | long runs are cut at spaces (quotes stay verbatim) | test_F07 |
| F10 | High | Sample deadline was a fixed 2026 date: after it passed, the demo told a different story ("No current page confirms it") | sample dates move with today | test_F10 |
| F09 | Med | If no page could be read, the report said "not found in the 0 pages reviewed" (false claim) and drafted an email | honest verdict; no email | test_F09 |
| F11 | Med | "Changed since last check" could be caused by choosing different sources, not by the pages changing | explicit warning when the source set differs | test_F11 |
| F12 | Med | API accepted any content-type, so a cross-site form post could trigger server fetches | require application/json (forces a CORS preflight) | test_F12 |
| F13 | Med | A gzip response was decoded as garbage, producing false "not found" gaps | refuse compressed bodies with a clear message | test_F13 |
| F14 | Med | A slow-drip server held a function for 24+ s (cost, and near Vercel's limit) | total 15 s deadline across redirects and reads | test_F14 |
| F20 | Med | Rate limit trusted X-Forwarded-For everywhere, so it was trivially bypassed off Vercel | trusted only when VERCEL is set | test_F20 |
| F05 | Med | A bogus charset in a response header crashed that fetch (500) | fall back to UTF-8 | test_F05 |
| F15 | Low | IPv6 was tried first, which fails on IPv4-only networks | IPv4 first (all addresses still validated) | test_F15 |
| F06 | Low | Malformed URLs (bad port, empty label, unclosed bracket) raised ValueError/UnicodeError instead of a friendly message | all become "That link is not valid." | test_F06 |
| F21 | Low | Deeply nested JSON gave a 500 | 400 | test_F21 |
| F08 | Low | Local dev server 404'd on `/?utm=x` (Vercel was unaffected) | query strings stripped | test_F08 |

Also: reader recall was 56% on paraphrased deadlines/fees (see below); the rate limit was hard-coded, now `DARKSPOT_RATE`.

## Things that were tested and held up
Pinned-IP TLS still rejects a certificate for the wrong hostname (F16); absurd numbers and lone surrogates do not crash; 400 random hostile documents
never crash and never produce a quote that is not a verbatim substring; pathological HTML finishes in under 1 s; corrupt, blank and encrypted PDFs get clear
messages; forged evidence (authority, name, url, time) is rejected when DARKSPOT_SECRET is set; injected instructions cannot change findings; 40 parallel
runs give identical results; real `api/*.py` entrypoints work from another working directory; hostile markup renders as inert text (0 injected elements);
no horizontal scroll at 375 px; WCAG AA text contrast in light and dark; keyboard-only use; focus indicators; failure and double-click handling; blocked localStorage.

## Coverage
| Layer | What | Result |
|---|---|---|
| Unit + integration | tests/test_core.py, tests/test_hardening.py | 46 pass |
| System (backend) | tests/system/probe_backend_adversarial.py (20), probe_fuzz_integration.py (10) | 30 pass |
| System (browser, Chromium) | tests/system/probe_browser.py (incl. redesign, a11y, contrast, drag-drop, CSP) | 17 pass |
| Mutation check | 12 defects re-introduced one at a time | 12 of 12 caught |
| Accuracy | tests/system/eval_rule_reader.py, 24 hand-written cases | recall 56% -> 93%, 0 false reports |

## Limits of this testing (read before trusting the numbers)
- The 93% is measured on the same 24 cases used to tune the reader, so it is optimistic. No held-out set or real-world pages were used.
- Not tested: a real Vercel deployment, real internet and real HTTPS sites, the Claude reader/checklist, Brave search, Firefox/Safari/real phones, screen readers,
  Windows paths, Python 3.10/3.11 (only 3.12 here; CI is configured for 3.10 and 3.12 but has not run).
- The rate limiter is per instance. Use Vercel Firewall rules for a real limit.
- Contrast was measured on text; borders and focus-ring contrast were not.
- Server date is UTC; users in other time zones can see staleness off by up to a day.

## v6 addendum (changes made after a judge-style review)
Changes: "What the sources say" table (`overview` in the analyze response); reader now treats "final date" as a deadline and "nobody / no one / none / no need" as negation, and also keeps a later negated sentence
when an earlier sentence already matched the same docs/text item; free-text items found on several pages are "Unclear", not "Confirmed" (code cannot compare free text); the server recomputes source
authority and rejects a client that changes it (this works with or without DARKSPOT_SECRET); UI wording for the optional AI reader; `anthropic` pinned.
Re-run on v6: 54 unit/integration tests pass (46 old + 8 new in tests/test_v6.py); backend adversarial, fuzz/integration and 17 browser probes pass with no failures; reader eval unchanged at 14/15 on the tuned set (the "Submit your form by" case is still missed).
Also done by hand: demo flow over HTTP, fetch of three real HTTPS pages (a JavaScript-heavy page returned almost no text, as documented), a 375 px layout check of the new table.
Not re-run: mutation check. Still not tested: real Vercel deployment, live Claude calls, Brave search, Python 3.10/3.11, CI on GitHub.

## v7 addendum (innovation pass)
Added `darkspot/signals.py`: cycle drift, source hedges, derived open questions, verification impact path, report fingerprint. Two fictional sample pages were extended (blog: "2024-25 intake"; college page: "amounts are subject to change") so the demo shows the new signals.
Re-run on v7 in the build sandbox: 71 unit/integration tests pass (54 old + 17 new in tests/test_v7.py, including a 300-document fuzz proving cycle and hedge quotes are always verbatim); backend adversarial 21/21, fuzz/integration 10/10, browser 17/17 (CSP clean, no overflow at 375 px, contrast AA); reader eval unchanged (14/15 on the tuned set).
Limits: cycle detection needs an explicit year range (2024-25, 2024/2025) or a word form ("intake 2024"); hedge detection is a fixed phrase list; the readiness path is a what-if on fixed heuristic weights, not a prediction. Mutation check not re-run. Still not tested: real Vercel deployment, live Claude calls, Brave search, Python 3.10/3.11, real-internet pages.
