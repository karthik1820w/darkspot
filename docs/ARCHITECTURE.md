# Architecture (stateless, client-orchestrated)

Why: Vercel functions are short-lived, share no memory and have request-size and duration limits. So there is no long-lived connection and no
server-side session. The browser drives six stages as small independent requests and carries state between them.

    Browser (public/: no build, CSP-safe, text-only rendering, localStorage for the last check)
      1 validate question
      2 POST /api/checklist    expected-answer checklist (template | Claude proposal, validated; optional search discovery)
      3 POST /api/sources x N  in PARALLEL, one source each: fetch / PDF / text / sample -> clean text, date, authority, sha256, time, HMAC
      4+5 POST /api/analyze    verify verbatim, compare, copy-detect, score, diff vs previous snapshot, email draft
      6 render: source-by-item table (overview), Sourced / Derived / Suggested lanes, side-by-side conflicts, changes, exports
    api/*.py = three 5-line Vercel functions.  darkspot/api.py = all logic, shared with `python -m darkspot`.

Rules: extractors only FIND quotes; code decides states. Every quote must exist verbatim in the stored text. Model output is validated and capped.
Trust boundary: the browser echoes sources back to /api/analyze, so the server recomputes hash, flags, dates and staleness, and (with
DARKSPOT_SECRET) verifies an HMAC over name, url, hash, date, authority and time. Without the secret, integrity is not enforced.
Security: http/https and ports 80/443 only; DNS resolved once, all addresses must be public, and the connection goes to that exact IP while TLS
verifies the hostname (no rebinding window); every redirect hop re-validated; size and time caps; PDF magic-byte check, page cap, no encrypted files;
the model gets no tools; injection phrases flagged; CSP default-src 'none' (same string in vercel.json and code, enforced by a test); 4 MB body cap; generic errors.
Known gaps: per-instance rate limit (use Vercel Firewall); no auth; confidence and readiness not calibrated on labelled data; Claude, Brave and Vercel paths untested here.
