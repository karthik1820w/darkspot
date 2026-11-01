# DarkSpot: find what your sources leave out

Enter a question and add pages. DarkSpot quotes facts, compares pages, and lists conflicts, gaps and outdated details as a checklist, each with the exact quote behind it.

## Run (no installs needed, Python 3.10+)
    python -m darkspot          # open http://127.0.0.1:8000, press "Try a sample"
    python -m unittest tests.test_core -v

Offline mode uses a deterministic rule-based reader and works without a key or network (links need network).
Live mode (optional, **not run in the build sandbox**): `pip install anthropic`, set `ANTHROPIC_API_KEY` and `DARKSPOT_MODEL`, send `"mode":"claude"` to `/api/analyze`.

## Honest limits
Findings are signals, not facts. "Missing" means not found in the pages reviewed. The rule reader fits the scholarship template; other topics need the live reader and new slot templates. Pages that need JavaScript, PDFs and logins are not read (paste text instead). Sample pages are fictional.
See docs/ARCHITECTURE.md.
