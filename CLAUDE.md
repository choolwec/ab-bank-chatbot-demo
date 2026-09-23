# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

V1 (deterministic core, no LLM) of a customer-facing chatbot for AB Bank
Zambia — informational, lead-generating, and complaint/fraud-routing only.
Every answer in `knowledge/` is draft content pending legal sign-off (search
for `[CONFIRM` to find every unverified fact — contacts, hours, branch data).
Built to the spec in `../technical-build-plan.md` (§3) in the parent project
folder; every design rule referenced there (§1, §3.1-§3.4) maps to code here.

**Rescope in progress (2026-09-23):** the bot is being extended from
website-only to website + WhatsApp + Facebook Messenger. Research, the target
architecture (channel adapters around the unchanged router), Zambian
legal constraints, and the phased plan are in `docs/multi-platform-research.md`.
Until that work lands, everything below describes the website-only V1.
Conversational-quality research (repair patterns from Rasa/Parlant/etc., a
15-case probe of where the current router breaks, and a tiered plan) is in
`docs/conversational-research.md`. **`docs/excellence-plan.md` is the master
plan** tying both together: measurable quality bar, target architecture,
small-model/Jev findings, eval harness, phased roadmap. Its matcher numbers
come from `research/matcher-benchmark/` (research-only code, not part of the
app or test suite; `python research/matcher-benchmark/bench_matcher.py`).
**`docs/execution-plan.md` is the week-by-week build plan**: every ticket
(S1, C6, W2…) with its spec, tests, acceptance criteria and dependencies.
Work one ticket per branch (`feat/<ID>-<slug>`) and update its Status in
that plan's Appendix A in the same PR.

## Commands

Setup (Windows):
```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Run the server:
```powershell
.venv\Scripts\python -m uvicorn app.main:app --reload
# http://127.0.0.1:8000 — demo page with the widget bottom-right
```

Tests:
```powershell
.venv\Scripts\python -m pytest -q                          # full suite
.venv\Scripts\python -m pytest tests/test_flows.py -q      # one file
.venv\Scripts\python -m pytest tests/test_matcher.py::test_name -q  # one test
```
The full suite must pass before any commit — **content edits are deploys**
(see below).

Admin scripts:
```powershell
.venv\Scripts\python -m admin.report --days 7   # weekly metrics + top unmatched utterances
.venv\Scripts\python -m admin.legal_export       # regenerate docs/intent-review.md for legal sign-off
```

Kill switches — take effect immediately, no restart: edit `flags.json`, or
set env vars `FREE_TEXT_ENABLED` / `WIDGET_ENABLED` (env wins over file, file
wins over the default in `app/config.py`).

## Architecture

### Request pipeline (`app/router.py`)
Every inbound message runs through, in order: **guards → session-control
payloads → "talk to a person" → urgent-topic scan → active flow → quick-reply
payload → abuse check → free-text matcher → confidence-gated response**. The
order is load-bearing, not incidental:
- `app/guards.py` masks PII (card/NRC/account/PIN numbers) *before* anything
  else — including the audit log — ever sees the raw text.
- The urgent-topic scan (`guards.urgent_scan`) runs on **every** message
  regardless of active flow, and fraud/lost-card reports preempt any
  in-progress flow except an already-active fraud/complaint one.
- Every reply is guaranteed at least one button before `handle()` returns —
  a hard "no dead ends" invariant enforced in code, not a per-answer
  convention to remember.
- Two unmatched free-text messages in a row (`session.strikes`) force a
  human-handoff offer instead of a third guess.

### Free-text matching (`app/matcher.py`)
Fully local, no external API: TF-IDF over character n-grams
(misspelling-tolerant) blended with RapidFuzz ratios, scored per intent
against its `phrases:` list from `knowledge/intents/*.yaml`.
`HIGH_CONFIDENCE`/`MEDIUM_CONFIDENCE` thresholds in `app/config.py` decide
between a direct answer, a "did you mean…?" suggestion, or a fallback/strike.

### Priority flows (`app/flows/`)
Fraud, complaint, lead-capture, and branch-locator are deterministic
step-form state machines (`FormFlow` in `flows/base.py`) — never
AI-generated. State lives on the session (`session.flow_state`), not on the
flow object, so one flow instance is stateless and shared across sessions.
Fraud/complaint flows always end in a ticket (`audit.create_ticket`) that
only a human closes — the bot never marks its own case resolved.

### Session store (`app/session.py`)
In-memory, single-process by design (`SessionStore` behind a lock, 30-minute
idle timeout). This is why `app/main.py`'s deployment notes insist on
exactly **one** uvicorn worker/process: sessions here and the per-IP
rate-limit buckets in `app/main.py` both live in process memory, so extra
workers or instances silently fragment conversations and rate limits across
processes. Scaling past one process means moving sessions to SQLite/Redis —
a real code change, not a config flag.

### Audit trail (`app/audit.py`)
SQLite (`data/audit.db`) + append-only JSONL, written only after guards have
masked the text — nothing unmasked ever reaches storage. Tickets
(fraud/complaint/callback) carry the full masked transcript so a human
handoff never makes a customer repeat themselves. `purge_expired()` enforces
`TRANSCRIPT_RETENTION_DAYS`/`TICKET_RETENTION_DAYS`, both currently
placeholders pending legal.

### Contact-center handoff (`app/jira_export.py`)
The contact center runs on Jira already and didn't want a second queue to
watch, so every `audit.create_ticket()` call also best-effort pushes a Jira
issue via `_push_to_jira()` — wrapped so a Jira outage/bad creds can never
block the customer-facing ticket flow. Gated by `JIRA_ENABLED` (kill switch,
same flags.json/env-var mechanism as everything else); currently `true` in
`flags.json` but no real credentials are set
(`JIRA_BASE_URL`/`JIRA_EMAIL`/`JIRA_API_TOKEN`/`JIRA_PROJECT_KEY`), so
`config.jira_configured()` is `False` and every push falls into **mock
mode**: a synthetic issue (fake key like `CC-3`, correct priority/labels/
summary/full transcript) is appended to `data/jira_mock.jsonl` instead of
calling the network. `GET /admin/jira-preview` renders those mock issues as
Jira-style cards — this is what the demo uses to show "what will land in
the contact center's Jira" without real Jira access. No auth on that route
yet: fine pre-launch, must be gated before it carries real customer data.
Once those four env vars are set (see `docs/deployment-and-jira-setup.md`
for where each one comes from — self-service via the contact-center team's
own Jira login in most cases, not necessarily IT), setting them flips
`_push_real()` on (plain REST v2 issue creation, Basic Auth) with no other
code change.

### Knowledge base = content, not code (`knowledge/`)
`intents/*.yaml` (schema documented in a comment block at the top of
`intents/smalltalk.yaml`) holds phrases/answers/buttons; `branches.json`
holds branch/agent locator data; `faq/*.md` is source prose intended for a
future RAG layer and is not currently loaded by the running app. **Content
edits are deploys**: the regression suite asserts every declared phrase
actually matches its own intent, that no answer is a dead end, and that PII
patterns are caught — run `pytest` before every commit, and git history is
the compliance audit trail for wording changes. `INSTRUCTIONS.md` is the
non-technical version of this same workflow, written for non-engineers
editing content directly.

### Widget (`widget/`)
Vanilla JS/CSS, zero dependencies, WCAG 2.1 AA. Same-domain embed is a
single `<script src=".../widget/widget.js" defer>`; cross-domain embed
(e.g. loaded from a WordPress site while the backend lives elsewhere) just
adds `data-endpoint="https://<backend-host>"` — this was built in from the
start, so cross-origin embedding needs no widget code change, only a CORS
allowlist change server-side (`ALLOWED_ORIGINS` in `app/config.py`). The
widget self-hides if `/health` reports `widget_enabled: false` or is
unreachable.

### WordPress plugin (`wordpress-plugin/`)
A single flat file, `ab-bank-chatbot.php` (plain WordPress plugin format,
no build step, deliberately no subfolder) that outputs the cross-domain
widget `<script>` tag via WordPress's own Settings screen. Not part of the
Python app or its test suite — see `wordpress-plugin/README.md`. Confirmed
2026-07-22: the site is self-hosted WordPress (wordpress.org), not
WordPress.com, so there's no plan-tier restriction on installing it.

It was originally shipped as a zip of a subfolder
(`ab-bank-chatbot/ab-bank-chatbot.php`) and activation failed with "plugin
file does not exist" even though the name showed up correctly in the
Plugins list. One confirmed real bug: the zip's internal path was stored
with a Windows backslash instead of a forward slash (both Explorer's "Send
to > Compressed folder" and PowerShell's `Compress-Archive` were observed
doing this on this machine), which WordPress's Linux-hosted unzip doesn't
treat as a directory separator. **That fix alone did not resolve it for
the user**, so flattening to a single root-level file (this version)
removes the folder-structure question entirely rather than relying on the
zip being built correctly — see `wordpress-plugin/README.md`'s
Troubleshooting section for the other suspects (stale leftover from the
failed attempt, a host security scanner quarantining the file, PclZip
fallback bugs) if this still fails.

## Invariants to preserve when changing code

- Nothing downstream of `guards.mask()` (matcher, flows, audit log) may ever
  see unmasked PII.
- The guaranteed-button invariant on the final reply in `router.handle()`
  must not be bypassed.
- Fraud/complaint flows must never mark their own ticket resolved.
- In production behind a reverse proxy, `PROXY_HOPS` must be set or the rate
  limiter collapses every visitor onto the proxy's own IP (see
  `app/main.py::_client_ip`).
