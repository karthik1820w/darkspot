# STACK.md (shared record for the frontend and backend work)

## Stack (chosen by the project owner; kept as is)
- Frontend: plain HTML, CSS and vanilla JavaScript in `public/` (no build step). Strict CSP: scripts and styles from 'self' only, text rendered with textContent.
- Backend: Python standard library, stateless. Three Vercel functions in `api/*.py` (5 lines each) share all logic in `darkspot/api.py`; `python -m darkspot` serves the same functions locally.
- Dependencies: `pypdf==5.9.0` (PDF text), `anthropic==1.17.0` (optional AI reader). No database; saved checks live in the browser's localStorage.

## API (all POST, `Content-Type: application/json`, body max 4 MB)
| Route | Request | Response |
|---|---|---|
| `/api/checklist` | `question`, `template` (auto/scholarship/visa/general), `mode` (rules/claude), `discover` | `origin`, `items[]`, `urls[]`, `warning` |
| `/api/sources` | one of `url` / `text` / `pdf{name,b64}` / `sample` (1-3), plus `idx` | one source: text, date, authority, sha256, `sig` |
| `/api/analyze` | `question`, `checklist`, `sources[]` (max 6), `previous` | verdict, readiness, `items[]`, `confirmed[]`, **`overview{sources[],rows[]}`**, sources, duplicates, changes, email_draft, **`cycles`, `hedges`, `questions`, `independence`, `fingerprint`**, `readiness.path`, `items[].impact` / `items[].caveats` |

`overview.rows[].cells` maps a source id to a list of `{text, quote, flags[]}`; a missing source id means "not found on that page".

## Environment variables
`DARKSPOT_SECRET` (sign evidence; set it on public deployments), `ANTHROPIC_API_KEY` + `DARKSPOT_MODEL` (optional AI reader; anyone can then trigger paid calls), `BRAVE_API_KEY` (optional search), `DARKSPOT_RATE` (requests/min/client, default 60), `DARKSPOT_HOST`, `DARKSPOT_PORT`.

## Rules the code relies on
Source authority is decided on the server, never taken from the client. Every quote must exist verbatim in the stored page text. Free-text items are never auto-confirmed.
