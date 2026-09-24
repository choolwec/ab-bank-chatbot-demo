# Remaining work: implementation plan

Written 2026-09-24, at commit `500a056`, after Phases 0–1, most of Phase 2,
Phase 3a (except P7/P9), WhatsApp W2–W9, Messenger M1–M5, and H1/H3.
This picks up where [`execution-plan.md`](execution-plan.md) Appendix A shows
☐ or ◐. It adds what building the finished tickets taught us: design
decisions already fixed in code, the exact files each ticket touches, and
the traps found on the way.

**Ground rules (unchanged):** work lands on `master` with the full suite
green, and each ticket updates its row in `execution-plan.md` Appendix A in
the same commit. New customer wording goes in YAML with `status: draft`,
never as a Python literal (the AST test enforces this). A gate is never
loosened without a written reason in `tests/eval/gates*.yaml`. Write patch
scripts with a file, not a shell heredoc: heredocs on this Windows machine
corrupted `\n` and `\b` escapes several times.

---

## Update 24/09/2026

Draft for review by the PO. This section supersedes sections 1-2 below where
they differ; the ticket plans in section 3 are kept as the design record.

### What is now built

| Ticket | Built | Where to read more |
|---|---|---|
| R1 | `/health` `checks` (counts only), `admin/alerts.py` posting to a Teams group chat (Power Automate Workflow, `ALERT_TEAMS_WEBHOOK_URL`) and Jira (`chatbot-alert`), nightly retention purges including `inbox.db` (`app/housekeeping.py`), extra checks `flags_file` (Sev 1) and `webhook_rejected` (Sev 2) | `runbook-incidents.md` |
| P7 | `deploy/` (systemd, nginx, deploy/rollback/backup/restore, `admin.sh`, `env.example`, crontab, logrotate), `ABZ_DATA_DIR` / `ABZ_FLAGS_FILE`, rotatable `REPLY_KEY` (`admin.rotate_reply_key`), hermetic suite, shellcheck in CI | `runbook-production.md` |
| P9 | `research/load/load.py`, `/admin/timing`, real Jira push moved off the request path; local 5-minute run: `/chat` p95 18.9 ms, no errors | `load-test-results.md` |
| H5 | Sampled one-tap CSAT (20% by `user_hash`, never after fraud, once per session) | CLAUDE.md, request pipeline |
| H6 | Weekly report v2 written to `data/report.md`: per channel, launch targets PASS/FAIL/n/a, WhatsApp cost estimate (US$, [VERIFY]), leads, campaigns | `admin/report.py` |
| H2 | Chatwoot desk for WhatsApp handoffs (`app/desk/`), masked and phone-redacted, `CHATWOOT_ENABLED` kill switch | `chatwoot-setup.md` |
| H4 | `admin/export_bot_wrong.py`: `bot-wrong` labels from Chatwoot and Jira into `data/utterances.csv` | `chatwoot-setup.md` |
| Matcher | Negation handled in both modes, `out_of_scope` phrases, broader phrases, recalibration (`EMB_MEDIUM` 0.435), gates tightened. Character: right 0.670 / wrong 0.044 / OOS 0.067. Hybrid: right 0.835 / wrong 0.022 / OOS 0.067 (targets 0.85 / 0.02 / 0.03) | `metrics-matcher-2026-09-24.md` |
| MK2 | Marketing-consent step in the callback flow (`MARKETING_CONSENT_ENABLED`), opt-out commands, Jira label `marketing-consent` | `marketing-launch-kit.md` |
| MK3 | Campaign source (widget `data-campaign`/utm, WhatsApp `ref:`), "Continue on WhatsApp" link (`WA_LINK_ENABLED`, off), a callback button on every product answer | `marketing-launch-kit.md` |
| Launch docs | `go-no-go.md` (R2), `pilot-runbook-whatsapp.md` (W10), `hosting-requirements-it.md`, `meta-onboarding-guide.md` (W1), `legal-compliance-pack.md`, `dpia-draft.md`, `phrase-workshop-kit.md`, `decisions-log.md` | branch `wip/launch-docs-review`, **not yet merged** into this branch |

Section 4 loose ends now closed: the inbox purge is scheduled (R1); backups
cover `user_key_secret` and `reply_key`, and `REPLY_KEY` can be rotated (P7);
`render.yaml` fetches the model and runs shadow mode (P7); the suite no
longer writes to `data/` (P7); README and INSTRUCTIONS list the admin
commands and content files (this update). The "Hybrid matcher switch-over"
items 1-3 are done; the shadow reviews and the flag flip remain.

Being fixed in parallel, not in this branch yet: CSAT keeping "Talk to a
person", a distinct `request_callback` payload, email masking before
Chatwoot, the desk-failure message, start-up purge resilience, the crontab
and nginx changes, and the WhatsApp coexistence pause (W11,
`COEXISTENCE_ENABLED`).

### What remains, by owner

| Owner | What |
|---|---|
| IT | Lusaka VM (2 vCPU / 4 GB / 40 GB), DMZ HTTPS endpoint, TLS certificate (bank or Let's Encrypt), outbound HTTPS to `graph.facebook.com` and to `huggingface.co` during deploys, an off-VM backup destination in Zambia, the second VM for Chatwoot, and access logs that do not record the Chatwoot webhook path |
| PO | Create the Teams Workflow and hand over its URL (runbook-incidents section 5); decide the items in the concerns table below; Meta onboarding (W1); confirm the public WhatsApp number before `WA_LINK_ENABLED` goes on; run the weekly shadow reviews, then decide on `EMBEDDINGS_ENABLED`; a paid Render disk if a week of staging shadow data is wanted; sign the go/no-go tables |
| Legal / Compliance / DPO | Sign off `intent-review.md` (new consent, opt-out, CSAT and desk wording); consent and opt-out rules under the ECT Act 2021 and Data Protection Act 2021; retention periods (including whether the JSONL audit copy may be deleted after 90 days while tickets are kept); whether Jira on Atlassian Cloud is a cross-border transfer; the DPIA; the [CONFIRM] items in both runbooks and the marketing kit. Every statutory reference must be checked against the official text |
| Contact-centre lead | Review the `desk.*` staff notes; Chatwoot agent training (W19); pilot roles and testers |
| Marketing | MK1 launch communications; name an owner for opt-out suppression (opt-outs exist only as `marketing_opt_out` audit events keyed by `user_hash`); campaign codes |
| Content owner + staff | N1 phrase workshop and two-person labelling; N8 native-speaker check of the draft Bemba/Nyanja phrases (`mwabuka shani`, `mulishani`, `ndifuna loan`, `ndefwaya loan`) |
| Dev | P7 acceptance on the VM (two deploys, two rollbacks, one restore; a dry run of `deploy.sh` as the non-root user); P9 30-minute staging and VM runs; switch on the alerts cron line; W11; the [VERIFY] checks against a live Chatwoot, Meta and the bank's Jira; the parallel fixes above; a decision on the serial WhatsApp send worker (about 1.6 messages/s at 250 ms per Graph call) before volume grows |

### Decision recorded: env file mode 640

`/etc/abz-chatbot/env` is `root:abz`, mode `640`, with single-quoted values.
Reason: the alert cron job in `runbook-incidents.md` section 6 runs as the
service user `abz` and sources the env file, and the files it writes in
`data/` must stay writable by the app. The extra exposure is small, because
the app process, running as `abz`, already holds these secrets in its
environment.

**Not yet reconciled in code:** `deploy/lib.sh` `check_env` still refuses
any mode but `600`, and `deploy/env.example`, `deploy/abz-chatbot.service`
and `runbook-production.md` still say `600`. `deploy/crontab.example`
instead runs alerts as root through `admin.sh`, which works with `600`.
Either change `check_env` and those files to `640`, or keep `600` with the
`admin.sh` cron line (or a systemd timer). Settle this before the first
deploy, or `deploy.sh` will refuse a `640` file.

### Reviewer concerns that need a human decision

| # | Concern | Who decides | Status |
|---|---|---|---|
| 1 | After a Teams "Resolved" post, a re-firing issue waits out the 15-minute limit. In a crash-restart loop the chat can show "Resolved" for up to about 14 minutes while the bot is down. Options: repost a re-firing Sev 1 at once, or hold "Resolved" posts for 15 minutes | PO | Open |
| 2 | `inbox.py` stores the handler's exception text in failed rows; raw PII could land in `inbox.db` if an exception ever includes it. Suggest storing the exception type only | Dev + PO | Open |
| 3 | A `/health` 503 (app up, store unreadable) raises "The chatbot is not responding" (Sev 1); the wording could mislead the responder | PO | Open |
| 4 | A locked or corrupt database stops start-up (the start-up purge is not wrapped); an invalid `PURGE_HOUR` silently ends the nightly task | Dev | In progress (parallel fix) |
| 5 | `/health` is public and shows operational counts and invalid flag names (no ids or text). IT may want nginx to limit the detail to internal addresses | IT | Open |
| 6 | A real Jira push runs in a daemon thread; a restart mid-push loses it (the local ticket is safe). Needs a retry or outbox before real Jira credentials go live | PO + Dev | Open |
| 7 | nginx sets X-Frame-Options/frame-ancestors on every path, `/widget/` included. Harmless while the widget is a script; it would break an iframe widget | Dev | Noted |
| 8 | `backup.sh` runs `sqlite3` as root on WAL-mode databases; consider running the backup step as `abz` | Dev | Open |
| 9 | CSAT on WhatsApp and Messenger merges into the resolving bubble and drops its "Talk to a person" and "Done" buttons | PO | In progress (parallel fix) |
| 10 | Web rate-limit hits are never logged, so the report's "Rate limited" line always shows 0 for the web | Dev | Open |
| 11 | The report's "Topics as typed (masked)" table gives Marketing free text; personal names inside it would not be caught. Free text, or topic groups only? | PO + DPO | Open |
| 12 | The lead section counts `marketing_consent` values `true`/`"true"` as yes, as well as `"yes"`. The flow writes `yes`/`no`/`not_asked`; confirm and tighten | Dev | Open |
| 13 | If opening the Chatwoot conversation fails, the customer has already been told a person will reply there, but the bot is not paused | PO + CC | In progress (parallel fix) |
| 14 | Email addresses are not masked before reaching Chatwoot | DPO | In progress (parallel fix) |
| 15 | The Chatwoot webhook secret sits in the URL path, so access logs that record paths would hold it | IT | In progress (nginx) |
| 16 | While the desk has a conversation, urgent messages (fraud, lost card) are only forwarded to the agent and do not start the fraud flow (same as Messenger M4) | PO + Ops | Open |
| 17 | Launch in hybrid mode although neither mode meets all the section 1 targets (hybrid right 0.835, wrong 0.022, OOS 0.067). Hybrid BANKING77 wrong answers are 0.031 (mostly fraud reports routed as lost card; both reach the fraud flow) | PO | Open |
| 18 | The matcher builder read a doc quoting 12 held-out items and removed 8 phrases that exactly matched eval items: a mild fit to the eval sets. The N1 golden set and shadow reviews are the independent check | PO | Noted |
| 19 | "Request a callback" on product answers uses `human_handoff`; on Messenger, and on WhatsApp with Chatwoot, it opens a live handoff, so no consent is asked and no source is recorded | PO | In progress (parallel fix: `request_callback`) |
| 20 | Campaign source is logged as a separate `session_source` event rather than on the session-start event | PO | Open |
| 21 | `guards.yes_no` counts loose replies such as "sure" as marketing consent. Does that meet the ECT Act 2021 opt-in standard? | Legal | Open |
| 22 | The Contact Centre number 888 appears in the marketing kit's anti-scam copy without a [CONFIRM] marker at every use | Marketing + Legal | Open |
| 23 | The WhatsApp coexistence pause (bot stops when staff reply from the Business app) was not built; needed before the staff pilot if decision D5 (coexistence) stands | Dev | In progress (W11) |
| 24 | Tickets with names and phone numbers go to Jira; if Jira is Atlassian Cloud this is likely a cross-border transfer. Real Jira stays in mock mode until Legal rules | Legal | Open |
| 25 | The single WhatsApp send worker is serial (about 1.6 messages/s) | PO + Dev | Open |
| 26 | Env file mode 600 or 640 (see above) | Dev | Decided 640; code not yet aligned |

---

## 1. Where things stand

| Area | State |
|---|---|
| Suite | 566 tests, ~110 s locally (about 40 s of it is the embedding tests). CI green through `edc4919`; `500a056` was still running when this was written. |
| Safety | Fraud recall on BANKING77: rules 75.4%, rules + model 79.4%; 0 false fraud triggers on our 88 ordinary in-scope questions. |
| Understanding (production = character matcher) | right 0.527 · wrong 0.044 · out-of-scope 0.100 · large out-of-scope set 0.155 |
| Understanding (hybrid, behind `EMBEDDINGS_ENABLED`, off) | right 0.758 · wrong 0.044 · out-of-scope 0.133 · large set 0.066 |
| Channels | Web live. WhatsApp and Messenger complete against recorded payloads, running in mock mode until Meta credentials exist. |

### Remaining tickets at a glance

| ID | What | Who | Blocked on | Effort |
|---|---|---|---|---|
| H5 | Sampled one-tap CSAT | Dev | — | 1 d |
| H6 | Weekly quality report v2 | Dev | H5 (for CSAT) | 2 d |
| R1 | Incident runbook, `/health` checks, alert script | Dev + PO | — (the alert destination needs a decision) | 2 d |
| P7 | `deploy/` + production runbook | Dev | **Lusaka VM (H-P)** for acceptance | 2 d build + 1 d on the VM |
| P9 | Load and soak test | Dev | P7 for the production run | 1 d |
| H2 | Chatwoot agent desk | Dev | **Chatwoot VM**; licence check | 5–6 d |
| H4 | "Bot got this wrong" loop | Dev | H2 (Chatwoot labels) or Jira labels | 1.5 d |
| — | Hybrid switch-over (negation fix + two shadow reviews) | Dev + CO | N4 reviews on real traffic | 2 d + 2 weeks |
| N1 ◐ | Golden set: workshop + two-person labelling | CO + staff | Staff trial (W03+) | people time |
| N8 ◐ | ≥ 100 code-mixed phrases + model comparison | CO + Dev | N1 workshop | 1 d dev |
| R2 | Go/no-go checklists | PO | — | 0.5 d (draftable now) |
| W10 | WhatsApp pilot runbook | PO + CC | — | 0.5 d (draftable now) |
| K2 | Resolve every `[CONFIRM` | Business | — | people time |
| W1, L1–L8, H-P, O1, O2, MK1 | Non-engineering tracks | PO, Legal, Ops, Marketing | — | calendar time |

**Engineering left: about 16 developer-days**, plus time on the two VMs once
they exist.

---

## 2. Order of work

1. **Now, no dependencies:** H5 → H6 → R1 (code half) → P7 (build half) → P9
   (local run) → R2 and W10 drafts. About 8 days.
2. **As soon as the Chatwoot VM exists:** H2 → H4. About 7 days.
3. **During the staff trial:** N1 workshop and labelling; N8 phrases; run
   shadow mode (`SHADOW_MATCHER=true` on staging); fix negation; two weekly
   reviews; then switch `EMBEDDINGS_ENABLED`.
4. **When the Lusaka VM is delivered:** P7 acceptance (deploy twice, roll
   back twice, restore a backup), P9 production run, R1 alerts pointed at
   real destinations.
5. **Gates:** R2 checklists signed for M3 → M6.

---

## 3. Ticket-by-ticket plans

### H5 · Sampled one-tap CSAT (1 day)

**Design:**
- A conversation counts as *resolved* when either of these happens:
  - the customer is answered by `thanks_goodbye`;
  - a callback or complaint finishes with a ticket.

  Exclude fraud: asking "how did we do?" right after a fraud report reads
  badly.
- **Sample 20% deterministically:**
  `int(session.user_hash[:8], 16) % 5 == 0`. It's stable per customer and
  testable. Ask at most once per session (`session.slots["csat_asked"]`).
- Append a second reply, which P5 merges on WhatsApp and Messenger:
  `msg("csat.ask")` with buttons `button("csat_up", "csat:up")` 👍 and
  `button("csat_down", "csat:down")` 👎. Both labels are ≤ 20 characters.
- The router handles the `csat:up` / `csat:down` payloads before intents.
  Log `action=csat:up|down` with the channel, reply `msg("csat.thanks")`,
  and keep the menu buttons. A 👎 also offers "Talk to a person".
- On WhatsApp this is inside the 24-h window (a service message).
  `CSAT_SAMPLE_RATE` goes in config, so Ops can lower it if costs matter.

**Files:** `app/router.py` (the `_answer` path for `thanks_goodbye`, and the
payload branch), `app/flows/lead.py` and `app/flows/complaint.py` (the
`finish()` replies), `app/config.py`, `knowledge/system_messages.yaml`.

**Tests:** a sampled session gets the question once and a non-sampled one
never does; a tap is logged with its channel; no CSAT after fraud; the
render-limit test covers the CSAT reply.

### H6 · Weekly quality report v2 (2 days)

**Design.** Extend `admin/report.py`, keeping its CLI, and write
`data/report.md`. Everything is computed from audit `action` values that
already exist:

| Report line | Source actions |
|---|---|
| Conversations, per channel | distinct `session_id` by `channel` |
| Strikes per conversation, two-strike handoffs | `fallback`, `two_strike` |
| Repairs | `repeat`, `clarify` |
| Frustration, abuse | `frustration`, `abuse` |
| Digressions resumed | `digression:*` |
| Corrections | **new**: log `action=correction` in `FormFlow._apply_correction` (not logged today) |
| Cancel confirmations and outcomes | `cancel_confirm`, `cancel`, `cancel_declined` |
| Urgent asks and outcomes | `urgent_confirm:*`, `urgent:*`, `urgent_declined` |
| Context boosts, two-question answers | `context_boost`, and meta `intents` (**new**: log `action=multi_answer`) |
| Out of scope | `out_of_scope` |
| Tickets by type and channel | `tickets` table |
| Delivery failures | `send_failed`, `wa_status:failed` |
| Rate limiting, pauses | `rate_limited`, `paused` |
| Shadow agreement | `shadow` (the `agree` field) |
| CSAT | `csat:up`, `csat:down` (H5) |
| Estimated WhatsApp cost | bot messages on `whatsapp` beyond the free tier × `WA_UTILITY_RATE` (config, [VERIFY] the current Meta rate card) |

Then every §1 target from `excellence-plan.md` with ✅/❌: fraud recall (from
the eval gates), out-of-scope ≤ 3%, right ≥ 85%, wrong ≤ 2%, ≤ 4 bot
messages per conversation, delivery failures ≤ 1%, CSAT ≥ 4.2
(👍 share × 5), and handoff SLA once H2 exists. Also keep today's "top
unmatched" list.

**Tests:** seed a temp audit DB with known events. Check every line's
numbers, the per-channel split, the ✅/❌ logic, and that no raw id appears
in the report.

### R1 · Runbooks and alerts (2 days: code + doc)

**Code:**
- `/health` gains a `checks` object: worker queue age
  (`inbox.oldest_pending_age()`), failed inbox rows, send failures and
  webhook 5xx in the last hour, and whether the embedding model verified.
  HTTP stays 200 unless the app itself is broken; uptime checkers read
  `checks.*.ok`.
- A small middleware counts webhook 4xx/5xx in memory.
- `admin/alerts.py`: run by cron every minute on the VM. It compares the
  checks with thresholds (`/health` down; webhook 5xx > 1%; send failures
  > 2%; queue older than 2 minutes) and posts to `ALERT_TEAMS_WEBHOOK_URL`
  (a Teams group chat, through a Power Automate Workflow) and to Jira via
  `jira_export.push_alert`. Teams is limited to one post per issue per 15
  minutes plus one "Resolved" post; Jira to one issue per issue per 24 h.
- **Schedule the missing purges:** `inbox.purge()` exists but nothing calls
  it. Call it from lifespan and the nightly job, alongside
  `audit.purge_expired()` and `store.purge_expired()`.

**Doc:** `docs/runbook-incidents.md` holds the severity table from the plan
and first steps per severity. It includes the exact kill-switch commands for
the PO and CC lead: `flags.json` edits for `FREE_TEXT_ENABLED`,
`WHATSAPP_ENABLED`, `MESSENGER_ENABLED`, `WIDGET_ENABLED`,
`URGENT_MODEL_ENABLED` and `EMBEDDINGS_ENABLED`. It also covers "Meta
webhook-failure emails go to <shared inbox>", on-call hours, and a
post-mortem template.

**Tests:** `/health` checks under a stale queue, failed rows and send
failures; alert thresholds and rate-limiting with a mocked transport.

### P7 · Production hosting in Lusaka (2 days build now, 1 day on the VM)

**Build now, in `deploy/`:**
- `abz-chatbot.service`: systemd, **one** uvicorn worker, `Restart=always`,
  `EnvironmentFile=/etc/abz-chatbot/env`, and a non-root user. (This plan
  first said root-only `chmod 600`; the decision is now `root:abz` mode
  `640`, see "Update 24/09/2026" below.)
- `nginx.conf`: TLS (Let's Encrypt or the bank certificate), and
  `proxy_set_header X-Forwarded-For`, with `PROXY_HOPS=1` in the env file.
  Pass `/webhooks/*` through with the **raw body untouched**, since the
  signatures depend on it. Limit client body size.
- `backup.sh`: nightly `sqlite3 .backup` of `audit.db`, `sessions.db` and
  `inbox.db`. Keep 14 days, with an off-VM copy inside Zambia. **It must also
  back up `data/user_key_secret` and `data/reply_key`**, or set
  `USER_KEY_SECRET` and `REPLY_KEY` in the env file and back up that file
  instead:
  - losing the reply key makes every sealed reply address unreadable;
  - losing the hash secret breaks per-customer continuity in reports.
- `logrotate` config; `deploy.sh`: fetch the **release tag** (never a branch),
  `pip install -r requirements.txt`, `python -m admin.fetch_model`,
  `pytest -q`, and restart only if the tests pass.
- `docs/runbook-production.md`: deploy, roll back to the previous tag,
  restore a backup, rotate each secret, and the full env-var list:
  - `WA_*`, `MS_*`, `JIRA_*`, `ADMIN_*`, `USER_KEY_SECRET`, `REPLY_KEY`;
  - `ALLOWED_ORIGINS`, `PROXY_HOPS`, the retention days;
  - `EMB_*`, `CHATWOOT_*`, `ALERT_TEAMS_WEBHOOK_URL` and the other
    `ALERT_*` settings, `PURGE_HOUR`.

**On the VM (acceptance):** two deploys, two rollbacks, one successful
restore, and `/health` green from outside the network.

**Tests now:** `shellcheck` on the scripts in CI, and a test that `deploy/`
never contains a secret-looking value.

### P9 · Load and soak test (1 day)

`research/load/load.py` uses async `httpx` (already a dependency) and mixes
traffic:
- 70% `/chat` conversations from real paths (FAQ, fraud report, callback);
- 30% signed WhatsApp webhook posts, using `tests/data/wa/*.json` with
  fresh message ids.

It runs at 20 messages/s for 30 minutes. It records server-side p95, from
the audit timestamps or a timing middleware, plus client p95, RSS every 30
seconds, and the inbox queue age. The targets are **p95 ≤ 150 ms and no
memory growth**. Run it locally now to find problems early, on staging,
then on production before M3. Things to watch:
- SQLite lock contention between the worker and `/chat`;
- `SessionStore` per-key lock growth;
- embedding latency if `EMBEDDINGS_ENABLED`.

Record the results in `docs/load-test-results.md`.

### H2 · Chatwoot agent desk (5–6 days)

**Before starting:**
- Confirm the Chatwoot edition's licence **[VERIFY]**. Community is MIT;
  Enterprise features are not.
- Confirm the webhook authentication Chatwoot offers **[VERIFY]**. If it
  has no signature, use a long secret in the webhook URL path, compared in
  constant time.

**Design:**
- **Keep the channels ourselves** (research §7.6). Chatwoot gets an
  **API-channel** inbox.
- `app/desk/chatwoot.py`: a thin `httpx` client. It creates or looks up a
  contact by `identifier = user_hash` (name only if the customer gave one),
  creates the conversation, and posts the masked transcript as a **private
  note**. It stores `jira_key`/ticket `ref` as conversation custom
  attributes and sets the status to *open*.
- **Handoff:**
  - `config.handoff_mode("whatsapp")` already becomes `"inbox"` when
    `CHATWOOT_URL` is set. `router._handoff_to_inbox` already creates the
    handoff ticket and sets `session.slots["handoff_requested"]`.
  - Add a `pass_to_desk()` step to the WhatsApp sender, mirroring
    Messenger's `pass_to_inbox()`: create the Chatwoot conversation and
    pause the bot.
  - Store `chatwoot_conversation_id` on the session.
  - The web can join later as live chat.
- **Customer messages while paused:** today these are logged and not
  answered. Also **forward them** to the Chatwoot conversation as incoming
  messages, masked.
- **Agent replies:** `POST /webhooks/chatwoot/<secret>` receives
  `message_created` events that are outgoing and not private. Look up the
  session by conversation id, then call the channel adapter's
  `send_free_form()`. On `WindowClosed`, post a private note back ("24 h
  window closed: send the `case_update` template from /admin/cases") and
  don't send.
- **Resolved:** `conversation_status_changed` to resolved calls
  `resume_bot(session)`. Unpause after 24 h idle as a fallback.
- Jira stays the system of record for fraud and complaints.

**Tests:** the whole round trip with `httpx.MockTransport`:
- handoff creates the contact, conversation and note;
- a customer message while paused is forwarded;
- an agent reply is sent to WhatsApp;
- an agent reply after 24 h is refused, with the note posted back;
- resolve resumes the bot;
- a bad webhook secret gets 403;
- no raw phone number reaches Chatwoot (only `user_hash`, and the transcript
  is masked).

**People:** CC trains agents in W19.

### H4 · "Bot got this wrong" loop (1.5 days)

- `admin/export_bot_wrong.py` pulls conversations labelled `bot-wrong` from
  Chatwoot's API, and issues with the `bot-wrong` label from Jira (JQL),
  over the last 7 days.
- It keeps only customer turns, re-runs the same second PII check as
  `admin/export_utterances.py`, and appends them to the labelling CSV
  (`data/utterances.csv`) with `source=bot-wrong`.
- That feeds the normal N1 flow: two reviewers, then `import_labels`.
- A weekly cron sits next to the H6 report.

**Tests:** mocked Chatwoot/Jira responses; de-duplication against the
existing CSV; PII drop.

### Hybrid matcher switch-over (2 days dev + 2 weeks of shadow reviews)

The hybrid matcher is ready, but three known issues stand between it and
production (`tests/test_embeddings.py::KNOWN_HYBRID_DIFFERENCES`):

1. **Negation.** "I don't want a loan, I want to open an account" gets "did
   you mean" instead of the answer. Fix it deterministically: when a clause
   is negated ("don't want / not / no …"), drop it before embedding and
   score the remaining clause. Reuse the C10 clause splitter and the S1
   negation regexes.
2. **Held-out out-of-scope, 0.100 → 0.133:** "how do i open a facebook
   account" and "reset my facebook password" are answered.
3. **BANKING77 wrong answers, 0.008 → 0.031.**

For 2 and 3: add `out_of_scope` phrases in the *embedding* style (short
topical sentences about other platforms and services). Then re-run
`python -m admin.calibrate` and **tighten, never loosen**,
`gates_embeddings.yaml`.

Then run `SHADOW_MATCHER=true` on staging and in production. Hold two
weekly `admin.shadow_report` reviews, and switch only if the shadow is right
on ≥ 80% of disagreements and never worse on out of scope. Flip
`EMBEDDINGS_ENABLED=true` in `flags.json`: no deploy needed, and it's
instantly reversible. Make sure `deploy.sh` has run `fetch_model` first.

### N1 ◐ · Golden set (people, with tooling done)

1. W04 staff workshop, 2 hours, with the social-media and contact-centre
   teams: ≥ 15 phrasings per intent.
2. Staff trial on staging, then
   `python -m admin.export_utterances --days 7` weekly.
3. Two reviewers fill `label_a` and `label_b`; then run
   `python -m admin.import_labels data/utterances.csv`. The PO settles
   disagreements.
4. Once `golden.yaml` has ≥ 30 per intent, add golden gates to both gate
   files at their measured values, and re-run `admin.calibrate`, which
   already pools the golden set.
5. A second reviewer checks the BANKING77 mapping in
   `admin/import_banking77.py`.

Mark N1 ☑ after step 4.

### N8 ◐ · Code-mixed (1 day dev after the data exists)

Replace `tests/eval/code_mixed.yaml` with ≥ 100 workshop phrases, checked by
Bemba and Nyanja speakers, and remove `seed_unverified`. Then:
- run `python -m admin.eval_code_mixed`, adding `--model-dir` for each
  candidate: multilingual MiniLM-L12 (Apache-2.0) and multilingual-e5-small
  (MIT, needs the `query:` prefix);
- switch models only if code-mixed accuracy improves **and** both gate
  files still pass. A new model needs its own pinned revision and sha256 in
  `config.EMBED_MODEL_SHA256`, then `admin.calibrate` and
  `admin.calibrate_urgent` again.

Whatever the model decision, add the verified phrases' *vocabulary* to
intent phrases through normal content work. Never copy the eval items
themselves.

### R2 · Go/no-go checklists (PO, draftable now)

`docs/go-no-go.md` holds one table per milestone, signed in the release-tag
commit:
- **M3 (web):** every `[CONFIRM` resolved; Legal sign-off of
  `docs/intent-review.md` (answers, system messages, templates, channel
  variants); P7 accepted; L1, L3, L4, L8; R1 live; §1 safety targets met;
  `ADMIN_*` and `USER_KEY_SECRET`/`REPLY_KEY` set and backed up.
- **M4 (WhatsApp):** M3, plus L2, W1, templates approved by Meta, and the
  staff pilot's go/no-go (W10).
- **M5 (Messenger):** App Review passed (M1 pack), and the Page Inbox
  handover tested with the social team.
- **M6 (full launch):** H2 live and agents trained, §1 targets met on 2
  weeks of real traffic per channel, MK1 ready.

### W10 · WhatsApp pilot runbook (PO + CC, draftable now)

`docs/pilot-runbook-whatsapp.md`:
- **Staff pilot, W15–W16:** about 30 staff; a daily 15-minute defect triage
  of the H6 report plus `bot-wrong` tags; a severity mapping to R1.
- **Limited public pilot, W17+:** a branch QR code and the website's
  "Continue on WhatsApp" link only. The widget change is small: a
  `wa.me/260769651262` button with no session data in the URL.
- **Go/no-go per stage:** §1 targets on pilot data, no Sev-1 in 7 days,
  handoff SLA ≥ 95%.

### K2 · Resolve every `[CONFIRM` (business owners)

`python -m admin.legal_export` lists them. There are 20 in code and
content today, including items added during this build:

| Item | Where | Owner |
|---|---|---|
| 24-h emergency / card-block line (it drives every fraud message) | `app/config.py` `emergency_phone` | Ops |
| Tariff URL | `app/config.py` | Marketing |
| Branch phones, sort codes, branch-count discrepancy | `knowledge/branches.json` | Ops |
| **Exact branch coordinates** (approximate area pins today, `coords_verified: false`) | `knowledge/branches.json` | Ops |
| **Saturday Contact Centre hours; the public-holiday list** | `app/config.py` `CONTACT_CENTRE_HOURS`, `PUBLIC_HOLIDAYS` | CC / Ops |
| Saturday branch opening time conflict | `locations.yaml` `opening_hours` | CC |
| PIN / MyABZ reset routes | `urgent.yaml` `credential_trouble` | Ops |
| Service-status page | `technical.yaml` | IT |
| Finding a nearby agent | `system_messages.yaml` `locator.agents` | eTumba team |
| Complaint response-time commitment (BoZ Directive) | `system_messages.yaml` `complaint.finish` | Compliance |

Also resolve the **[VERIFY]** items in code before go-live:
- `WA_GRAPH_VERSION`;
- the BSUID field names in `whatsapp._user_key`;
- `PAGE_INBOX_APP_ID`, and the handover/standby semantics;
- the Messenger App Review permission names;
- the Messenger profile limits.

---

## 4. Loose ends found during the build

- **Inbox purge is never scheduled.** Done in R1 (`app/housekeeping.py`).
- **Keys in `data/`** (`user_key_secret`, `reply_key`) are production
  secrets. Covered in P7's backups. Rotating `REPLY_KEY` needs a
  re-encryption step (a `MultiFernet` with the old and new keys); add that
  to the rotation runbook.
- **Render staging** doesn't run `admin.fetch_model`, so hybrid mode and N7
  are silently off there. Add the fetch to `render.yaml`'s build command if
  staging should mirror production.
- **Test data:** tests using the `client` fixture still write to the real
  `data/` (sessions, audit, the Jira mock). Moving `client` onto
  `isolated_data` would make the suite hermetic.
- **Suite time** is ~110 s. If it becomes a problem, mark the embedding
  tests `slow` and run them in a separate CI job.
- **Docs to refresh:**
  - `README.md` needs the new admin commands: `eval_report`,
    `baseline_report`, `calibrate`, `calibrate_urgent`, `fetch_model`,
    `shadow_report`, `export_utterances`, `import_labels`,
    `import_banking77`, `messenger_profile`, `eval_code_mixed`.
  - `INSTRUCTIONS.md` should cover `knowledge/templates.yaml` and
    `knowledge/urgent_exemplars.yaml` for content editors.
- **`docs/metrics-m1.md`** predates Phase 2. Generate a
  `docs/metrics-m2.md` snapshot with `python -m admin.baseline_report` once
  the golden set exists.
