# Architecture (six stages, streamed)

    Browser (ui/: no build, CSP-safe, text-only rendering, reads an NDJSON stream)
       | POST /api/analyze  -> response is NDJSON: {"stage","msg"} ... then {"done": result} | {"error"}
       | limits: 1.5 MB body, 6 sources, 3 PDFs, 12 req/min/IP, localhost bind
    server.py: validate (stage 1) -> run
    1 Question and goal   validate input, topic, reader mode
    2 Checklist           checklist.build: template | Claude proposal (validated by checklist.clean, falls back to rules)
    3 Sources             net.fetch (SSRF guard) | PDF text (pypdf) | pasted text | optional search discovery -> text.py (clean text, date, injection flag); authority tag by domain
    4 Extract + verify    extractor finds QUOTES only; facts.verify: quote must be verbatim in stored text, value re-derived by code; negation guard
    5 Compare + score     per slot: conflict | stale | confirmed | single | gap/unclear; confidence (rule-of-thumb); coverage meter
    6 Dashboard           Sourced / Derived / Suggested lanes, side-by-side conflicts, copy / .md / print

Design rules: AI/rules only find quotes; code decides states. No claim without a verbatim quote. Absence is always scoped to pages reviewed.
Model output (checklist items) is validated and capped; any failure falls back to rules.
Security: http/https and ports 80/443 only; each redirect hop re-resolved and checked for private IPs; size/time caps; no tools given to the model;
injection phrases flagged; text-only rendering; CSP default-src 'none'; PDFs: magic-byte check, page cap, encrypted refused.
Known gaps: DNS-rebinding race between check and connect (pin the IP for production); no authentication; in-memory rate limit;
live Claude and search paths untested here; confidence is not calibrated against labelled data.
