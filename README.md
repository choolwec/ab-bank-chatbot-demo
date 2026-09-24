# AB Bank Zambia Chatbot — V1 (deterministic core)

[![CI](https://github.com/choolwec/ab-bank-chatbot-demo/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/choolwec/ab-bank-chatbot-demo/actions/workflows/ci.yml)

Customer-facing website assistant: **informational, lead-generating, complaint-routing**.
Deliberately *not* transactional, no account access, no LLM in V1. Built to the spec in
`../technical-build-plan.md` (§3) — every design rule there maps to code here.

> **Status: scaffold with DRAFT content.** Every answer in `knowledge/` is a draft
> pending legal sign-off (§3.5). Search the repo for `[CONFIRM` to see every value
> that must be verified before launch.

> **Rescope (2026-09-23): website + WhatsApp + Facebook Messenger.** See
> `docs/multi-platform-research.md` for the research, architecture, legal
> constraints, cost model and phased plan. The WhatsApp and Messenger
> adapters are built and run in mock mode until Meta credentials exist.
> Where things stand on 24/09/2026: `docs/build-summary-2026-09-24.md`.
> `CLAUDE.md` is the up-to-date architecture reference.

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
  channels/        web, WhatsApp and Messenger adapters around the one router
  desk/            Chatwoot agent desk for WhatsApp handoffs (H2)
  health.py        /health checks read by admin/alerts.py (R1)
  housekeeping.py  retention purges at start-up and nightly
  campaign.py      campaign source attribution (MK3)
knowledge/
  intents/*.yaml   28 launch intents: phrases + approved answer + follow-up buttons
  faq/*.md         source content (basis for V2 RAG chunks)
  branches.json    branch + agent locator data  ← PLACEHOLDER, verify before launch
widget/            widget.js, widget.css, demo.html (embeddable, WCAG 2.1 AA build spec)
tests/             regression suite, PII tests, flow tests, red-team inputs
admin/             report, legal export, alerts, evaluation and labelling scripts (see below)
deploy/            production VM: systemd, nginx, deploy/rollback/backup scripts, env.example
docs/              plans, runbooks, review documents
data/              runtime SQLite/JSONL (gitignored)
```

## Kill switches (§3.3 — no redeploy needed)

Checked on **every request**: environment variable wins, then `flags.json`, then default.

| Flag | Off means |
|---|---|
| `FREE_TEXT_ENABLED` | menu-only mode; typed messages get the menu |
| `WIDGET_ENABLED` | `/chat` returns 503 and the widget hides itself gracefully |
| `JIRA_ENABLED` | tickets stay local only — no Jira push, mock or real |
| `WHATSAPP_ENABLED`, `MESSENGER_ENABLED` | that channel stops answering |
| `CHATWOOT_ENABLED` | new WhatsApp handoffs go to the callback flow, not the agent desk |
| `EMBEDDINGS_ENABLED` | character matcher only (off by default; needs a restart) |
| `URGENT_MODEL_ENABLED` | no model-based second urgent check |
| `SHADOW_MATCHER` | no shadow-mode logging (off by default) |
| `MARKETING_CONSENT_ENABLED` | the callback flow does not ask for marketing consent (tickets record `not_asked`) |
| `WA_LINK_ENABLED` | no "Continue on WhatsApp" link in the widget (off by default) |

Flip by editing `flags.json` (re-read live) or setting the env var (`0`/`false`).
Values in `flags.json` must be `true`/`false` without quotes: a quoted
`"false"` is ignored and the switch stays on (`/health` reports it under
`checks.flags_file`). `CSAT_SAMPLE_RATE` (0-1, default 0.2) is read the same
way. Step-by-step: `docs/runbook-incidents.md` section 4.

## Contact-center handoff (Jira)

The contact center works out of Jira, not a second inbox — so every ticket
(fraud/complaint/callback) also becomes a Jira issue via `app/jira_export.py`,
called best-effort from `audit.create_ticket()` (a Jira outage never blocks
the customer-facing flow). Two modes, decided automatically:

- **Mock** (current state — no credentials set): a synthetic issue (`CC-1`,
  `CC-2`, …) with the real fields, priority, and full masked transcript is
  appended to `data/jira_mock.jsonl`. View it rendered as Jira-style cards at
  **`GET /admin/jira-preview`** — this is what the demo uses to show what
  contact-center staff will see, with zero real Jira access. It needs HTTP
  Basic auth: set `ADMIN_USER` and `ADMIN_PASSWORD` (it returns 404 until
  both are set).
- **Real**: set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`,
  `JIRA_PROJECT_KEY` and issues are created for real via the Jira REST API
  (`/rest/api/2/issue`, Basic Auth) — no other code change needed.

## Content workflow (content edits are deploys — §6)

1. Edit `knowledge/intents/*.yaml` (or `branches.json` / `faq/*.md`)
2. `pytest -q` — the regression suite must pass (phrase coverage, no dead ends, PII)
3. Commit — **git history is the content audit trail**
4. Regenerate the legal review doc: `python -m admin.legal_export`

Intent schema is documented at the top of `knowledge/intents/smalltalk.yaml`.

## Deployment notes (read before hosting)

Production is planned on a VM in Lusaka, set up from `deploy/` (systemd,
nginx, deploy / rollback / backup / restore scripts, `env.example`,
crontab). Follow `docs/runbook-production.md`; incidents and alerts are in
`docs/runbook-incidents.md`, the Chatwoot agent desk in
`docs/chatwoot-setup.md`, and load-test results in
`docs/load-test-results.md`. `ABZ_DATA_DIR` and `ABZ_FLAGS_FILE` move the
data directory and `flags.json` outside the release directory.

IT is not supporting this project (confirmed 2026-07-22) — see
`docs/deployment-and-jira-setup.md` for the concrete no-IT hosting path
(Render's free tier, already configured via `render.yaml`). The rules below
apply regardless of who ends up hosting it:

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

`wordpress-plugin/ab-bank-chatbot.php` is a small single-file plugin that adds the widget via
WordPress's own Settings screen — no theme edits needed. See
`wordpress-plugin/README.md`. Confirmed 2026-07-22: this is self-hosted
WordPress (wordpress.org), so there's no plan-tier restriction on installing
custom plugins.

## Before launch — every `[CONFIRM …]` must be resolved

- Emergency / card-block line, customer-care phone + email (`app/config.py` CONTACTS, or env vars)
- Official tariff-guide URL and website URL
- Real branch list with addresses, phones, hours (`knowledge/branches.json`)
- Opening hours, eTumba registration steps, loan product specifics (intent YAMLs)
- Retention periods (legal): `TRANSCRIPT_RETENTION_DAYS`, `TICKET_RETENTION_DAYS`
- CORS: set `ALLOWED_ORIGINS` env var to the bank's domain in production
- Real Jira project/token (`JIRA_BASE_URL`/`JIRA_EMAIL`/`JIRA_API_TOKEN`/`JIRA_PROJECT_KEY` — see `docs/deployment-and-jira-setup.md` for who actually needs to provide these, not necessarily IT), and `ADMIN_USER`/`ADMIN_PASSWORD` set for the admin pages
- Legal sign-off of **all** answers; manual NVDA + keyboard-only pass (§3.5)
- The Teams Workflow URL handed over as `ALERT_TEAMS_WEBHOOK_URL`, and the alert cron entry installed (`docs/runbook-incidents.md`)
- Meta webhook-failure emails routed to a shared inbox; an uptime checker on `/health` `checks.*.ok`
- The public WhatsApp number confirmed (`WA_LINK_NUMBER`) before `WA_LINK_ENABLED` is switched on
- Legal review of the marketing-consent and opt-out wording and of `docs/marketing-launch-kit.md`
- Current status and open decisions: `docs/remaining-work-plan.md` ("Update 24/09/2026")

## Reports and admin commands

`admin.report` now **writes `data/report.md`** instead of printing: quality
per channel, launch targets as PASS / FAIL / n/a, tickets, CSAT, an
estimated WhatsApp cost (US$, illustrative rates marked [VERIFY]), leads and
campaigns, and the top unmatched questions. The figures are drafts for a
qualified person to check before they go into any management report.

```powershell
# Reports
.venv\Scripts\python -m admin.report --days 7            # writes data/report.md (--stdout prints, --out elsewhere, --skip-eval)
.venv\Scripts\python -m admin.baseline_report            # metrics snapshot (--out docs/metrics-m2.md)
.venv\Scripts\python -m admin.shadow_report --days 7     # shadow-mode disagreements for the weekly review
.venv\Scripts\python -m admin.legal_export               # regenerate docs/intent-review.md for Legal

# Evaluation and calibration
.venv\Scripts\python -m admin.eval_report                # held-out accuracy vs the E3 gates (--all)
.venv\Scripts\python -m admin.eval_code_mixed            # code-mixed set (--model-dir to compare a model)
.venv\Scripts\python -m admin.calibrate                  # EMB_HIGH / EMB_MEDIUM (calibration split only)
.venv\Scripts\python -m admin.calibrate_urgent           # EMB_URGENT for the model-based urgent check
.venv\Scripts\python -m admin.fetch_model                # download and verify the embedding model

# Labelling (golden set)
.venv\Scripts\python -m admin.export_utterances --days 30   # customer messages -> data/utterances.csv
.venv\Scripts\python -m admin.export_bot_wrong --days 7     # "bot got this wrong" turns from Chatwoot and Jira
.venv\Scripts\python -m admin.import_labels data/utterances.csv  # agreed labels -> tests/eval/golden.yaml
.venv\Scripts\python -m admin.import_banking77           # map BANKING77 onto our intents

# Operations
.venv\Scripts\python -m admin.alerts --dry-run           # R1 alert check (cron every minute on the VM; --test posts one card)
.venv\Scripts\python -m admin.rotate_reply_key --check   # REPLY_KEY rotation (--dry-run, --generate)
.venv\Scripts\python -m admin.messenger_profile          # Messenger Page profile (--apply to post it)
python research/load/load.py --spawn --rate 20 --minutes 5  # load test (docs/load-test-results.md)
```

On the production VM, run admin commands through
`sudo /opt/abz-chatbot/current/deploy/admin.sh <command> [args]` so they see
the service's environment.

## Deliberately not here (V1 scope)

No LLM calls, no account data, no credentials handling, no data leaving the server.
V2 (grounded LLM shell) adds `app/llm.py` + `app/rag.py` only after the legal ruling (§4/§7).
