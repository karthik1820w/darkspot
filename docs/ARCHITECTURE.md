# Architecture

    Browser (ui/: one page, no build, CSP-safe, text-only rendering)
       | POST /api/analyze  (limits: 1 MB body, 6 sources, 12 req/min/IP, localhost bind)
    server.py -> analyze.py
       1 load_sources: net.fetch (SSRF guard) | pasted text | samples -> text.py (clean text, page date, injection flag)
       2 extractor finds QUOTES per slot: RuleExtractor (offline) | ClaudeExtractor (Citations, optional)
       3 facts.verify: quote must be verbatim in stored text; value is re-derived from the quote by code
       4 compare per slot: conflict | stale (old page or past date) | confirmed | single
       5 empty slot -> term re-scan of all pages -> "unclear" or "gap" (scoped: "not found in N pages")
       6 rank: conflict > gap/unclear > stale > single; verdict counts items to verify

Design rules: AI/rules only find quotes; code decides states. No claim without a verbatim quote. Absence is always scoped to pages reviewed.
Security: http/https and ports 80/443 only; every redirect hop re-resolved and checked for private IPs; size/time caps; no tools given to the model; injection phrases flagged; text-only rendering; CSP default-src 'none'.
Known gaps: DNS-rebinding race between check and connect is not closed (pin the IP for production); no authentication; in-memory rate limit; live mode untested here.
