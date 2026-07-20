# AB Bank Zambia Chatbot — V1 (deterministic core)

Customer-facing website assistant: **informational, lead-generating, complaint-routing**.
Deliberately *not* transactional, no account access, no LLM in V1. Built to the spec in
`../technical-build-plan.md` (§3) — every design rule there maps to code here.

> **Status: scaffold with DRAFT content.** Every answer in `knowledge/` is a draft
> pending legal sign-off (§3.5). Search the repo for `[CONFIRM` to see every value
> that must be verified before launch.

## Quickstart (Windows)

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q          # regression suite must be green
.venv\Scripts\python -m uvicorn app.main:app --reload
# open http://127.0.0.1:8000  → demo page with the widget bottom-right
```

## Repo layout (mirrors build plan §3.2)

```
app/
  main.py          FastAPI: /chat, /health, widget static files, rate limiting
  router.py        per-message pipeline: guards → flows → matcher → response
  matcher.py       TF-IDF char n-grams + fuzzy scoring, confidence thresholds
  flows/           fraud.py, complaint.py, lead.py, locator.py (state machines)
  guards.py        PII detect/mask, urgent-keyword scan, input caps, abuse filter
  session.py       in-memory session store, context slots, 30-min timeout
  audit.py         structured SQLite + JSONL logging (always post-masking), tickets
  jira_export.py   contact-center handoff: pushes tickets to Jira (or a mock preview)
  config.py        thresholds, contacts, kill switches
knowledge/
  intents/*.yaml   28 launch intents: phrases + approved answer + follow-up buttons
  faq/*.md         source content (basis for V2 RAG chunks)
  branches.json    branch + agent locator data  ← PLACEHOLDER, verify before launch
widget/            widget.js, widget.css, demo.html (embeddable, WCAG 2.1 AA build spec)
tests/             regression suite, PII tests, flow tests, red-team inputs
admin/
  report.py        weekly metrics report (build plan §6)
  legal_export.py  regenerates docs/intent-review.md for legal sign-off
docs/              generated review documents
data/              runtime SQLite/JSONL (gitignored)
```

## Kill switches (§3.3 — no redeploy needed)

Checked on **every request**: environment variable wins, then `flags.json`, then default.

| Flag | Off means |
|---|---|
| `FREE_TEXT_ENABLED` | menu-only mode; typed messages get the menu |
| `WIDGET_ENABLED` | `/chat` returns 503 and the widget hides itself gracefully |
| `JIRA_ENABLED` | tickets stay local only — no Jira push, mock or real |

Flip by editing `flags.json` (re-read live) or setting the env var (`0`/`false`).

## Contact-center handoff (Jira)

The contact center works out of Jira, not a second inbox — so every ticket
(fraud/complaint/callback) also becomes a Jira issue via `app/jira_export.py`,
called best-effort from `audit.create_ticket()` (a Jira outage never blocks
the customer-facing flow). Two modes, decided automatically:

- **Mock** (current state — no credentials set): a synthetic issue (`CC-1`,
  `CC-2`, …) with the real fields, priority, and full masked transcript is
  appended to `data/jira_mock.jsonl`. View it rendered as Jira-style cards at
  **`GET /admin/jira-preview`** — this is what the demo uses to show what
  contact-center staff will see, with zero real Jira access. That route has
  no auth yet; gate it before it carries real customer data.
- **Real**: set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`,
  `JIRA_PROJECT_KEY` and issues are created for real via the Jira REST API
  (`/rest/api/2/issue`, Basic Auth) — no other code change needed.

## Content workflow (content edits are deploys — §6)

1. Edit `knowledge/intents/*.yaml` (or `branches.json` / `faq/*.md`)
2. `pytest -q` — the regression suite must pass (phrase coverage, no dead ends, PII)
3. Commit — **git history is the content audit trail**
4. Regenerate the legal review doc: `python -m admin.legal_export`

Intent schema is documented at the top of `knowledge/intents/smalltalk.yaml`.

## Deployment notes for IT (read before hosting)

- **Run exactly ONE process, ONE worker.** Sessions and rate-limit counters
  live in process memory (a deliberate simplicity choice at <100 users/month).
  `uvicorn app.main:app` with no `--workers` flag is correct; running multiple
  workers or instances "for reliability" silently fragments conversations and
  rate limits across processes. If the bot ever needs to scale past one
  process, sessions move to SQLite/Redis first — that's a code change, not a
  config change.
- **Behind a reverse proxy (nginx/IIS/load balancer), set `PROXY_HOPS`.**
  Default `0` rate-limits on the socket peer address, which behind a proxy is
  the proxy itself — all visitors would share one 20-messages/minute bucket.
  Set `PROXY_HOPS=1` (or the number of proxies you run) and the real client IP
  is read from `X-Forwarded-For`; make sure the proxy overwrites/appends that
  header rather than passing it through from clients.
- **CORS**: set `ALLOWED_ORIGINS=https://<bank domain>` (comma-separated if
  several). The dev default only allows localhost.
- HTTPS terminates at your existing setup; the app itself serves plain HTTP.

## Embedding on the WordPress site

`wordpress-plugin/ab-bank-chatbot/` is a small plugin that adds the widget via
WordPress's own Settings screen — no theme edits needed. See
`wordpress-plugin/README.md`, including the WordPress.com plan-tier caveat
(custom plugins need the Business plan or higher).

## Before launch — every `[CONFIRM …]` must be resolved

- Emergency / card-block line, customer-care phone + email (`app/config.py` CONTACTS, or env vars)
- Official tariff-guide URL and website URL
- Real branch list with addresses, phones, hours (`knowledge/branches.json`)
- Opening hours, eTumba registration steps, loan product specifics (intent YAMLs)
- Retention periods (legal): `TRANSCRIPT_RETENTION_DAYS`, `TICKET_RETENTION_DAYS`
- CORS: set `ALLOWED_ORIGINS` env var to the bank's domain in production
- Real Jira project/token from IT (`JIRA_BASE_URL`/`JIRA_EMAIL`/`JIRA_API_TOKEN`/`JIRA_PROJECT_KEY`), and auth added to `/admin/jira-preview` before go-live
- Legal sign-off of **all** answers; manual NVDA + keyboard-only pass (§3.5)

## Reports

```powershell
.venv\Scripts\python -m admin.report --days 7        # weekly metrics + top unmatched
```

## Deliberately not here (V1 scope)

No LLM calls, no account data, no credentials handling, no data leaving the server.
V2 (grounded LLM shell) adds `app/llm.py` + `app/rag.py` only after the legal ruling (§4/§7).
