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
The WhatsApp and Messenger adapters are built (mock mode until Meta
credentials exist); everything below describes all three channels.
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

**Progress (24/09/2026):** Phases 0-1 are done, and so is the engineering
for most of Phases 2-4: channels, R1 health and alerts, P7 `deploy/`, P9
local load test, H2 Chatwoot desk, H4-H6, and marketing consent and campaign
source (MK2/MK3). What is left is mostly people and infrastructure: the
Lusaka VMs, Meta onboarding, legal sign-off, the phrase workshop and shadow
reviews. `docs/remaining-work-plan.md` (its 24/09/2026 update) lists what
remains by owner, and `docs/build-summary-2026-09-24.md` is the product-owner
summary. `docs/metrics-baseline.md` / `docs/metrics-m1.md` are the before/after
for M1 (`python -m admin.baseline_report`), and
`docs/metrics-matcher-2026-09-24.md` has the current matcher numbers.
Operations: `docs/runbook-production.md` (deploy, roll back, restore, rotate)
and `docs/runbook-incidents.md` (severities, alerts, kill switches). The owner
has asked for work to land directly on `master`, not on per-ticket branches.

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
(see below). The suite is hermetic: the `client` fixture runs on an isolated
data directory, and a test asserts nothing is written to the real `data/`.
`tests/conftest.py` forces `CSAT_SAMPLE_RATE=0`, so CSAT tests switch it on
themselves.

Admin scripts (full list in `README.md`; on the VM run them through
`deploy/admin.sh <command>`):
```powershell
.venv\Scripts\python -m admin.report --days 7   # writes data/report.md (--stdout, --out, --skip-eval)
.venv\Scripts\python -m admin.legal_export       # regenerate docs/intent-review.md for legal sign-off
.venv\Scripts\python -m admin.eval_report        # held-out accuracy vs the E3 gates
.venv\Scripts\python -m admin.alerts --dry-run   # R1: cron runs it every minute on the VM (--test posts one card)
.venv\Scripts\python -m admin.rotate_reply_key   # re-encrypt sealed reply addresses with the primary REPLY_KEY
.venv\Scripts\python -m admin.export_bot_wrong --days 7  # H4: bot-wrong turns -> data/utterances.csv
```

Kill switches — take effect immediately, no restart (except
`EMBEDDINGS_ENABLED`): edit `flags.json`, or set the env var (env wins over
file, file wins over the default in `app/config.py`). Values must be JSON
`true`/`false` without quotes: `config.flag()` ignores a quoted `"false"` and
the switch stays at its default (usually on); `/health` `checks.flags_file`
catches this. An env var set in the production env file silently overrides
`flags.json`. Switches: `FREE_TEXT_ENABLED`, `WIDGET_ENABLED`,
`WHATSAPP_ENABLED`, `MESSENGER_ENABLED`, `JIRA_ENABLED`, `CHATWOOT_ENABLED`,
`EMBEDDINGS_ENABLED`, `URGENT_MODEL_ENABLED`, `SHADOW_MATCHER`,
`MESSENGER_PUBLIC_REPLIES`, `MARKETING_CONSENT_ENABLED`, `WA_LINK_ENABLED`,
`COEXISTENCE_ENABLED`; `CSAT_SAMPLE_RATE` (0-1) is
read the same way. Full steps: `docs/runbook-incidents.md` section 4.
`ABZ_DATA_DIR` and `ABZ_FLAGS_FILE` move `data/` and `flags.json` out of the
release directory (on the VM: `/var/lib/abz-chatbot`, `/etc/abz-chatbot`);
unset, they default to the repo's own.

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
- Marketing opt-out (MK2): whole-message "unsubscribe", "opt out", "stop
  offers", "stop marketing" and variants become the `marketing_opt_out`
  payload, handled with the session-control payloads. It logs
  `action=marketing_opt_out` (with `user_hash`), sets
  `slots["marketing_opt_out"]`, confirms, and re-asks any step in progress;
  a fraud report is never dropped. The bare word "stop" still cancels.
- CSAT (H5): `csat:up` / `csat:down` taps are handled right after "talk to a
  person", before flows and intents; only the first tap after the question
  counts, stale taps are logged `csat_ignored`. After a resolved turn
  (`thanks_goodbye` that is the last intent answered and not the first
  message, or a finished callback or complaint, flagged by an internal
  `resolved` key that is stripped before replies leave `handle()`), a
  deterministic sample (`CSAT_SAMPLE_RATE`, default 0.2, from `user_hash`)
  gets one question with Good / Not good / Main menu, at most once per
  session and never in a session that started a fraud report. "Not good"
  puts "Talk to a person" first.
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

### Channels (`app/channels/`)
Every channel turns its traffic into `channels.base.InboundMessage` and goes
through the same unchanged `router.handle()`, so the invariants hold per
channel by construction. `web.py` is the widget's synchronous `POST /chat`,
with the per-IP limiter (`app/ratelimit.py`). `whatsapp.py` and
`messenger.py` are webhook adapters (see their sections). `app/render.py` (P3) turns
replies into native payloads: WhatsApp reply buttons (<=3) or a list
(4-10, `short_label` as the row title), Messenger quick replies (<=13). It
may re-shape buttons but never drops "Talk to a person".
`tests/test_render_limits.py` renders every intent on every channel, so a
label or body that breaks a platform limit fails CI. Button ids are
self-describing (`loc_city:Lusaka`, `time:Morning`) because WhatsApp keeps
old buttons tappable. `main.py` is only
the app shell: CORS, `/health`, the demo page, admin routes (all behind
`adminauth.require_admin`, including `GET /admin/timing`, P9's server-side
latency windows), and mounting the channel routers.

**Campaign source (MK3, `app/campaign.py`).** The widget sends `source` with
every `/chat` post (its `data-campaign`, else `utm_campaign` / `utm_source`).
On WhatsApp a `ref:<code>` token in the prefilled text is stripped in
`messaging.process()` before routing, so the matcher, transcript and audit
never see it; a message that was only the token is routed as a greeting.
Both sides sanitise to `[a-z0-9_-]`, at most 40 characters, and reject 7+
digit runs or anything `guards.mask()` would mask, so a code cannot carry
PII. First touch wins (`slots["source"]`), logged once as
`action=session_source`; callback tickets carry it. With `WA_LINK_ENABLED`
(off) `/health` returns `wa_link`, and the widget shows "Continue on
WhatsApp" (`https://wa.me/<WA_LINK_NUMBER>?text=Hi ref:<source>`, no
session data). Messenger `m.me` referrals are not read yet.

**Coexistence (W11, `app/channels/coexistence.py`, off by default).** When
staff reply from the WhatsApp Business app on the same number, Meta's
`smb_message_echoes` event becomes an InboundMessage of kind "echo" (same
signature check, inbox and worker; the staff text is dropped on parse). It
pauses the bot for that customer through the same `bot_paused_until` pause
the desk and Messenger use, for `COEXISTENCE_PAUSE_HOURS` (12) after the last
echo, or until a whole-message menu command. A hard urgent signal while
paused still creates a fraud ticket and sends one draft safety reply per
pause. Audit actions: `human_reply_echo`, `human_reply_echo_ignored`,
`human_reply_echo_stale`, `coexistence_resumed`, `coexistence_urgent`,
`coexistence_urgent_repeat`, `coexistence_unfinished_ticket`. See
`docs/whatsapp-coexistence.md` for the [VERIFY] items.

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
" and " / " also " / "?" into exactly two clauses of 3+ words (the splitter
lives in `matcher.py`, shared with the negation filter; a negated clause is
never answered as a second question). If *both* get
a confident, different direct answer, both go in one reply, with up to 5
buttons merged. Otherwise nothing changes. Urgent messages never reach it.
A branch lookup counts as a direct answer when the clause names a branch or
town; the locator itself also answers straight away when its trigger does
("where is the kitwe branch").

**Local embeddings (N3/N5).** With `EMBEDDINGS_ENABLED` on (**off by
default** until the N4 shadow review), the matcher *ranks* by 0.5·character +
0.5·all-MiniLM-L6-v2 similarity. It *decides* (answer / did you mean /
fallback) on the embedding score alone, mapped by `matcher.calibrated()` so
`EMB_HIGH`/`EMB_MEDIUM` land on the usual thresholds. Letting the character
score also decide was measured and rejected: it brings back its confident
out-of-scope mistakes. The model (Apache-2.0) runs locally on CPU through
onnxruntime. Fetch it with `python -m admin.fetch_model`, which checks the
pinned revision and sha256 (`config.EMBED_MODEL_SHA256`); an unverified or
missing model means character mode, never a crash. Thresholds come from
`python -m admin.calibrate` (calibration split only). Hybrid-mode gates are in
`tests/eval/gates_embeddings.yaml`, and known differences from character mode
are a strict list in `tests/test_embeddings.py`; the one left is a bare
"loan" getting a direct answer. `EMB_HIGH` 0.715 / `EMB_MEDIUM` 0.435 are the
24/09/2026 calibration. Launch in hybrid mode is recommended once shadow mode
(`SHADOW_MATCHER=true`, on for staging in `render.yaml`) has had a weekly
`admin.shadow_report` review (`docs/metrics-matcher-2026-09-24.md`).

**Negation (both modes).** `matcher.drop_negated_clauses()` drops a clause
matching `guards.NEGATED_REQUEST_RE` (negated wanting or asking: "I don't
want a loan, I want an account", "not interested in", "instead of") before
scoring, only when 3+ words remain. Problem reports ("my card is not
working"), past tense ("I didn't want insurance but they charged me") and
"not sure…" are kept. `guards.NEGATOR` is shared with S1's
`NEGATED_COMPLAINT_RE`.

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

**Marketing consent (MK2).** The callback flow has an optional fifth step,
`marketing_consent`, after `time` and before the C7 summary, behind
`MARKETING_CONSENT_ENABLED` (on). The generic `FormFlow.skip_step` hook
leaves it out when the flag is off or the customer opted out this session:
a skipped field is not asked, summarised or offered under "Change
something", and `resume()` moves past a step that stops applying midway.
Consent needs a clear answer (the buttons, a typed yes/no or a small set
like "I agree"); anything else re-asks with the buttons, and it is never
changed through the C6 correction path. The ticket always carries
`marketing_consent` (`yes`/`no` with `marketing_consent_at`, or
`not_asked`) and `source`; Jira adds the label `marketing-consent` on yes
only. An opt-out during a callback turns that callback's consent to `no`.
The wording is `status: draft` with a `legal_note` that
`admin.legal_export` prints as "For Legal".

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

Sessions are purged on the `TRANSCRIPT_RETENTION_DAYS` schedule by
`app/housekeeping.py` `purge_all()`, which runs every retention rule (audit,
sessions, `inbox.db`, `desk.db`) at start-up and nightly at `PURGE_HOUR`
(02:00 Lusaka) in an in-process asyncio task; unprocessed inbox rows are
never purged. Always go
through `with store.session(key) as (session, created):` (or
`web_session(id)`). It holds a per-key lock and saves on exit, so two
requests for one customer never interleave.

This is why `app/main.py`'s deployment notes still insist on exactly **one**
uvicorn worker/process: the per-key locks, the per-IP rate-limit buckets and
the `/health` webhook and send counters live in process memory, so extra
workers would race on the same session row and fragment rate limits and
alert counts. Scaling out means moving locks and sessions to
Redis, a real code change, not a config flag.

### Audit trail (`app/audit.py`)
SQLite (`data/audit.db`) + append-only JSONL, written only after guards have
masked the text — nothing unmasked ever reaches storage. Tickets
(fraud/complaint/callback) carry the full masked transcript so a human
handoff never makes a customer repeat themselves. `purge_expired()` enforces
`TRANSCRIPT_RETENTION_DAYS`/`TICKET_RETENTION_DAYS`, both currently
placeholders pending legal.
Since P6 every event and ticket has a `channel`. The only customer
identity stored is `user_hash`, an HMAC of `channel:user_key` keyed by
`USER_KEY_SECRET` (`app/identity.py`; generated into `data/` if unset). A
raw phone number, BSUID or PSID is **never** logged; `Session.id` is random.
Tickets carry a minimised `reply_to` ({channel, user_hash}). Schema changes
go in `audit._MIGRATIONS` so existing databases upgrade in place (tickets
gained `jira_key` for H2). `REPLY_KEY` may be a comma-separated list read
through `MultiFernet`, primary first; `python -m admin.rotate_reply_key`
re-encrypts stored sealed values, after which the old key can go. Newer
actions: `correction` (flow and field name only, never the value),
`multi_answer`, `csat_asked`, `csat:up`/`csat:down`/`csat_ignored`,
`marketing_opt_out`, `session_source`, `desk_failed`.

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
code change. A real push runs in a background daemon thread on deep copies
of the ticket (P9: inline it raised `/chat` p95 to 322 ms); mock mode stays
inline so tests are deterministic. A push lost to a restart mid-flight is
not retried yet. `push_alert()` (R1) shares `_push_real`/`_push_mock`:
label `chatbot-alert` plus `sev1`/`sev2`, never `chatbot`, optional
`ALERT_JIRA_PROJECT_KEY`; alert cards also render on `/admin/jira-preview`.

### Health and alerts (`app/health.py`, `app/metrics.py`, `admin/alerts.py`, R1)
`/health` keeps its old fields and adds `checks`: counts only (no ids, no
text), each with an `ok`. Checks: `worker_queue`, `failed_messages` (last
hour; `urgent` counts rows whose masked text reads as fraud),
`send_failures`, `webhook_errors` (5xx rate), `webhook_rejected` (signed
Meta requests refused with a 4xx: a wrong secret), `embedding_model` (only
when a feature needs it), and `flags_file`. It stays HTTP 200 when a check
fails and answers 503 only when a store cannot be read. Rolling one-hour
counters come from a pure ASGI middleware on `/webhooks/*` and from the
senders (mock sends are not counted). Thresholds are `ALERT_*` in
`config.py`, applied by the app. `admin/alerts.py` (cron, every minute)
reads `GET /health` from outside the process (down only after 3 tries 10 s
apart) and posts an Adaptive Card to a Teams group chat through a Power
Automate Workflow webhook (`ALERT_TEAMS_WEBHOOK_URL`; unset = mock to
`data/alerts_mock.jsonl`) plus a Jira issue. Sev 1: `health_down`,
`flags_file`, or failed rows that read as fraud; everything else Sev 2.
Teams: at most one post per issue per 15 minutes and one "Resolved" post;
Jira: one issue per issue per 24 h, never closed by the script. It prints
nothing unless a send failed (exit 1), never prints the webhook URL, and
keeps state in `data/alerts_state.json`. Runbook:
`docs/runbook-incidents.md`.

### Agent desk (`app/desk/`, H2)
Only WhatsApp uses it; Messenger keeps its Page Inbox handover (M4) and the
web keeps tickets and callbacks. It is on only when `CHATWOOT_URL`,
`CHATWOOT_ACCOUNT_ID`, `CHATWOOT_INBOX_ID` and `CHATWOOT_API_TOKEN` are all
set, and `CHATWOOT_ENABLED` (kill switch) is on; otherwise behaviour is as
before. "Talk to a person" on WhatsApp goes through
`WhatsAppSender.pass_to_desk()` -> `bridge.open_conversation()`: a contact
(identifier `user_hash`; a name only if typed in a flow), a conversation in
the API-channel inbox with `ticket_ref`/`jira_key`/`channel` attributes, the
masked transcript as a private note, then the bot pauses
(`slots["chatwoot_conversation_id"]`). If opening fails the bot is not
paused and `desk_failed` is logged; the ticket and Jira stay the record.
While paused, customer messages (urgent ones included, as with M4) are only
forwarded, masked. `POST /webhooks/chatwoot/{secret}` (constant-time
compare, 403 on a wrong secret, 404 when unconfigured or the secret is
under 24 characters) sends outgoing non-private agent replies with
`send_free_form()`; after the 24-hour window it posts a private note and
sends nothing. Attachments are not sent. Resolving resumes the bot, and so
does the next customer message after `DESK_IDLE_HOURS` (24) with no agent
reply. `data/desk.db` maps conversation -> hashed session key and is purged
on `TRANSCRIPT_RETENTION_DAYS`. Staff notes are `desk.*` in
`system_messages.yaml`. Setup: `docs/chatwoot-setup.md`. H4's
`admin.export_bot_wrong` pulls `bot-wrong` labels from Chatwoot and Jira
into `data/utterances.csv` (`source` column) for the N1 labelling flow.

### Weekly report (`admin/report.py`, H6)
Writes `data/report.md` (`--stdout` prints, `--out` elsewhere): per-channel
quality, launch targets as PASS / FAIL / n/a (never a false PASS without
data), tickets, CSAT, an estimated WhatsApp cost in US$ only
(`WA_UTILITY_RATE`, `WA_FREE_SERVICE_MESSAGES`, both [VERIFY]), leads by
channel, topic group, source and consent, campaigns (sessions, callbacks and
consenting callbacks per source, opt-outs), and top unmatched. No names,
phone numbers, session ids or hashes. The figures are drafts for review.

### Production deployment (`deploy/`, P7)
systemd (`abz-chatbot.service`, **one** uvicorn worker, non-root user
`abz`), nginx (TLS 1.2/1.3, `X-Forwarded-For` appended so `PROXY_HOPS=1`,
webhook bodies passed byte for byte, `/admin/` limited to allow-listed
networks, no query strings in the access log), `deploy.sh` (only `vX.Y.Z`
tags, a virtualenv per release, `fetch_model` and the full suite as the app
user on scratch data before the symlink switch, automatic switch back if
`/health` fails), `rollback.sh` (release names only, never paths),
`backup.sh`/`restore.sh` (the three databases plus `user_key_secret` and
`reply_key`), `admin.sh`, logrotate, `crontab.example` and `env.example`
(every variable the app reads). Shellcheck runs in CI and a test forbids
secret-looking values in `deploy/`. `render.yaml` (staging) fetches the
model and runs `SHADOW_MATCHER=true`. Runbook: `docs/runbook-production.md`;
load results: `docs/load-test-results.md` (the single WhatsApp send worker
does about 1.6 messages/s at 250 ms per Graph call).

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
unreachable. It sends a campaign `source` with each post and shows
"Continue on WhatsApp" only when `/health` returns a `wa_link` matching
`^https://wa.me/<digits>$`.

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
- Nothing sent to Chatwoot may bypass `app/desk/bridge.desk_text()` (masks
  again, then redacts phone-number-shaped digits as `[PHONE REDACTED]`).
- `flags.json` values must be JSON booleans; anything else is silently
  ignored by `config.flag()` (the `/health` `flags_file` check is Sev 1).
- Internal reply keys (`yes`/`no`, `resolved`) never
  leave `handle()`; tests check each one.
- `/health` carries counts only: never an id, a user hash or message text.
- Internal markers such as a campaign `ref:` token are stripped before the
  router, matcher, transcript or audit sees the text.
- Tests never write to the real `data/`; new fixtures use the isolated data
  directory.
- An unasked customer is never recorded as consenting to marketing
  (`not_asked`, never `yes`).
