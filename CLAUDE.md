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

**Progress (2026-09-23):** Phase 0 (M0) and Phase 1 (M1) engineering are
done. `docs/metrics-baseline.md` is the before picture and `docs/metrics-m1.md`
the after (`python -m admin.baseline_report`). The owner has asked for work
to land directly on `master`, not on per-ticket branches.

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
.venv\Scripts\python -m admin.eval_report        # held-out accuracy vs the E3 gates
```

Kill switches — take effect immediately, no restart: edit `flags.json`, or
set env vars `FREE_TEXT_ENABLED` / `WIDGET_ENABLED` (env wins over file, file
wins over the default in `app/config.py`).

## Architecture

### Request pipeline (`app/router.py`)
Every inbound message runs through, in order: **guards → session-control
payloads → "talk to a person" → urgent-topic scan → active flow (with a
mid-flow FAQ interrupt check) → quick-reply payload → abuse check →
free-text matcher → confidence-gated response**. The order is load-bearing,
not incidental:
- `app/guards.py` masks PII (card/NRC/account/PIN numbers) *before* anything
  else — including the audit log — ever sees the raw text.
- The urgent-topic scan (`guards.urgent_scan`) runs on **every** message
  regardless of active flow, and fraud/lost-card reports preempt any
  in-progress flow except an already-active fraud/complaint one.
  It returns an `UrgentSignal` with a strength (ticket S1): **hard** signals
  (stole/scam/hacked/lost card…) start the flow at once; **soft** ones
  (money gone, "didn't make this transaction", a bare "complaint", questions
  *about* scams) ask a yes/no confirmation first, held in
  `session.slots["pending_urgent"]` for exactly one message. Negation
  suppresses soft signals only, never hard ones. A fraud/complaint intent
  reached only through the fuzzy matcher also asks first. Corpora live in
  `tests/data/urgent_*.txt`; extend them rather than the regexes alone.
- Typed commands (`router.COMMANDS`, ticket C2: cancel/stop, menu/0,
  agent/talk to a person, help) run right after the urgent scan and work in
  any state, exactly like their buttons, but only as the **whole** message
  ("cancel my card" stays a lost-card report). Leaving a fraud or complaint
  report, by button or typed, asks "Stop anyway?" first
  (`flow_state["confirm_cancel"]`). `COMMAND_ANSWERS` lists words that are a
  legitimate answer inside a flow ("agent" in the locator).
- After every reply the router records `session.expecting` (C3): the last
  reply's options plus the payloads a typed yes/no means, declared with
  internal `yes`/`no` keys on the reply dict (flows) or `on_yes`/`on_no` in
  an intent's YAML. Those keys are stripped before replies leave `handle()`.
  The next message can then be "yes", "2", or a typed button label. Numbered
  picks need at least 2 real options, so "2" at a free-text step stays an
  answer. Any other message clears the expectation.
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

**Context carry-over (C9).** An answered intent sets
`session.slots["context"]` for the next 2 messages. Its optional
`follow_ups: {generic intent: specific intent}` then applies to a short
(<= 8 words) message that refers back (a pronoun, "how much", "what do I
need"…). If one of the matcher's top 3 at `MEDIUM_CONFIDENCE` or above is a
mapped generic intent, the specific one answers: "how much does it cost?"
after Tamanga gets `fees_tamanga`. Every switch is logged as an
`action=context_boost` audit event.

**Two questions in one message (C10).** `router._two_questions` splits on
" and " / " also " / "?" into exactly two clauses of 3+ words. If *both* get
a confident, different direct answer, both go in one reply, with up to 5
buttons merged. Otherwise nothing changes. Urgent messages never reach it.
A branch lookup counts as a direct answer when the clause names a branch or
town; the locator itself also answers straight away when its trigger does
("where is the kitwe branch").

**Evaluation gates (E3).** `tests/test_eval_gates.py` scores the matcher on
the held-out set `tests/eval/heldout.yaml` at the production thresholds and
fails the build if any metric crosses `tests/eval/gates.yaml` (right/wrong
direct answers, out-of-scope answered directly, one-tap reach).
`python -m admin.eval_report` prints the same numbers with the failing items.
Ratchet rule: an improvement tightens its gate in the same commit; a gate is
never loosened without a written reason. Never copy held-out phrasings into
intent `phrases:` (a test enforces this).

### Priority flows (`app/flows/`)
Fraud, complaint, lead-capture, and branch-locator are deterministic
step-form state machines (`FormFlow` in `flows/base.py`) — never
AI-generated. State lives on the session (`session.flow_state`), not on the
flow object, so one flow instance is stateless and shared across sessions.
Fraud/complaint flows always end in a ticket (`audit.create_ticket`) that
only a human closes — the bot never marks its own case resolved.

Complaint and callback flows (`require_confirmation = True`, ticket C7) end
with "Here's what I'll send: Mary Banda · 0977 123 456 · a loan · Morning"
and **[Send it] [Change something]**. "Change something" offers one button
per field, re-asks just that field, then shows the summary again. The
**fraud flow deliberately has no confirmation step**, so a report goes out
as fast as possible; its finish message shows the summary instead. That
reverses the 2026-07-25 behaviour on purpose, per the execution plan.
Read-backs ("Got it: 0977 123 456.") ride on the same bubble as the next
prompt (`base._with_ack`), for the message budget. The fraud flow has a
mandatory `contact` step (phone, email or an explicit "skip" with the
consequence stated). It used to promise "a member of staff will contact
you" while collecting no way to reach the customer.

**Pre-fill (C8).** When the message that starts a fraud report is at least
5 words *and* states a fact, or is 10+ words, it becomes `what_happened`.
`app/extract.py` pulls when/channel/branch/amount from it, and one yes/no
question ("You said this happened yesterday, involving your card. Is that
right?") replaces up to three. "No, let me explain" falls back to the normal
questions, and steps already filled are skipped. `when` always keeps the
customer's own words; `when_hint` (an ISO date) is added only when
unambiguous. dateparser hits need a digit and must not be just a time, so
"I may have been scammed" and "10am" never become dates. Every date test
pins "now".

**Digressions and corrections (C6).** Every in-flow message is classified
before it is stored. A **digression** (`router._digression`) is an
unrelated question asked mid-flow. It is answered, and the current step is
re-asked on the same reply, with `flow_state` untouched and no strike. All
three conditions must hold:
1. the message is question-shaped (ends in "?" or starts with a question
   word);
2. the matcher's top intent is a plain answer at `HIGH_CONFIDENCE`
   (+0.05 inside fraud/complaint);
3. at a validated step, the message also fails the validator.

The question-shape test replaced the older opt-in `interruptible_fields`
list, and still keeps the two regressions that list existed for ("eTumba"
as a fraud channel, "Opening a business account" as a callback topic)
stored as answers: `tests/conversations/c6-*.yaml` pins both.

A **correction** (`FormFlow._correction`) needs a marker ("sorry",
"actually", "my number is"…) *and* a value that passes an **earlier**
validated step's validator. That field is updated and read back ("Thanks,
I've updated your phone to 0966 123 456"), then the current step (or the
summary) is re-asked. Only validated fields (`correctable`) can be
corrected this way. Phone numbers are stored in one canonical form
("0977123456") in every flow.

### Session store (`app/session.py`)
Persistent since P1: `SqliteSessionStore` (`data/sessions.db`, one row per
`channel:user_key`, state as JSON) survives restarts. `SessionStore` keeps the
same rules in memory for tests (`SESSION_STORE=memory` selects it at run
time). `Session.id` is always an opaque random id: it is what the audit log
sees, never a phone number or platform id. There are two timeouts, kept
separate on purpose:
- `IDLE_REGREET_MINUTES` (30): the widget greets again, but a half-finished
  flow is **kept** and resumed.
- `FLOW_EXPIRY_HOURS` (24, or **72** for fraud/complaint): the flow is
  dropped.

Sessions are purged on the `TRANSCRIPT_RETENTION_DAYS` schedule. Always go
through `with store.session(key) as (session, created):` (or
`web_session(id)`). It holds a per-key lock and saves on exit, so two
requests for one customer never interleave.

This is why `app/main.py`'s deployment notes still insist on exactly **one**
uvicorn worker/process: the per-key locks and the per-IP rate-limit buckets
live in process memory, so extra workers would race on the same session row
and fragment rate limits. Scaling out means moving locks and sessions to
Redis, a real code change, not a config flag.

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
the contact center's Jira" without real Jira access. Every `/admin/*` route is behind HTTP Basic auth
(`main.require_admin`, ticket P8): set `ADMIN_USER` and `ADMIN_PASSWORD`
to turn the admin pages on; with either unset they return **404**, so a
fresh deploy never exposes names, numbers or transcripts. New admin routes
must add `dependencies=[Depends(require_admin)]` (`tests/test_admin.py`
checks every registered `/admin` path).
Once those four env vars are set (see `docs/deployment-and-jira-setup.md`
for where each one comes from — self-service via the contact-center team's
own Jira login in most cases, not necessarily IT), setting them flips
`_push_real()` on (plain REST v2 issue creation, Basic Auth) with no other
code change.

### Knowledge base = content, not code (`knowledge/`)
`intents/*.yaml` (schema documented in a comment block at the top of
`intents/smalltalk.yaml`) holds phrases/answers/buttons; `branches.json`
holds branch/agent locator data; `system_messages.yaml` holds every
built-in text that isn't an intent answer (welcome, fallbacks, flow prompts,
retries, finish texts), read through `app/messages.msg(key, **fmt)`. No
customer-facing reply text or button label may be a Python literal (an
AST test enforces it). Buttons are built with `messages.button(key,
payload)` from `button.*` entries, 20 characters or fewer. Rotating
wrappers ("Got it." / "Thanks." / "Okay.") use `variant(key, n)`, picked by
turn number so tests stay deterministic; only wrappers vary, never facts. Flows look keys up by
convention (`<flow>.step.<field>`, `<flow>.retry.<field>`), and both
`messages.verify()` and `flows.verify_messages()` fail at import on a
missing key; `faq/*.md` is source prose intended for a
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
