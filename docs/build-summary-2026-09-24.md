# Build summary, 24/09/2026

> **Draft.** Prepared from the code and the build reports for the product
> owner. A qualified person must review it before it is shared or relied
> on. Nothing here is a legal or regulatory opinion; every reference to a
> law or Bank of Zambia requirement must be checked against the official
> text.

## Summary

The engineering for launch is largely built and tested (full suite: 895
tests passing). What stands between us and the website launch is now
mostly **people and infrastructure**, not code: the Lusaka server from IT,
Legal sign-off of the wording, the Teams alert chat, and Meta onboarding
for WhatsApp. Several decisions below need the product owner's yes or no.

## What was built

| Piece | What it does | Ready? |
|---|---|---|
| Health checks and alerts (R1) | `/health` reports the state of each part of the bot. A job every minute posts problems to a Microsoft Teams group chat and raises a Jira issue (Sev 1 or Sev 2). Old records are purged every night. | Built; needs the real Teams chat and Jira project |
| Production deployment (P7) | Scripts to install, update, roll back and back up the bot on a server in Lusaka. Data and settings live outside the program, so an update never loses them. | Built; needs the VM |
| Load test (P9) | A local 5-minute test at 20 messages a second: website replies in 18.9 ms (95th percentile), no errors. | Local run only; the 30-minute runs need staging and the VM |
| Customer feedback (H5) | One in five customers is asked "how did we do?" after a resolved conversation, never after a fraud report. | Done |
| Weekly report (H6) | Written to `data/report.md`: quality per channel, launch targets PASS/FAIL, tickets, feedback, leads and campaigns (counts only, no names or numbers). | Done |
| Agent desk for WhatsApp (H2, H4) | "Talk to a person" on WhatsApp opens a Chatwoot conversation for agents, with the customer's details masked. Agents can tag "bot got this wrong" to improve the bot. | Built; needs a second VM, a licence check and agent training |
| Better understanding | The bot now handles "I don't want X, I want Y", recognises more off-topic questions, and was recalibrated. See the numbers below. | Built; the better (hybrid) mode stays off until shadow reviews |
| Marketing consent and opt-out (MK2) | The callback request ends with an optional "may we send you news and offers?" question. Customers can type "unsubscribe" at any time. Jira tickets are labelled when the customer said yes. | Built; wording needs Legal |
| Campaign tracking (MK3) | Records which campaign or QR code brought a conversation, and can show a "Continue on WhatsApp" link on the website. | Built; link off until the WhatsApp number is confirmed |
| Launch documents | Go/no-go checklist, WhatsApp pilot runbook, IT hosting request, Meta onboarding guide, legal pack, draft DPIA, phrase-workshop kit, decisions log. | Drafted, in `docs/`; awaiting PO review |

**Understanding, measured on the held-out test set** (share of test
questions; detail in [metrics-matcher-2026-09-24.md](metrics-matcher-2026-09-24.md)):

| Measure | Current mode (live) | Hybrid mode (off) | Target |
|---|---|---|---|
| Right answer given directly | 0.670 | 0.835 | 0.85 or more |
| Wrong answer given directly | 0.044 | 0.022 | 0.02 or less |
| Off-topic question answered directly | 0.067 | 0.067 | 0.03 or less |

Neither mode meets every target yet. The samples are small (30 off-topic
items, so one item moves that figure by 0.033). More gains should come from
real phrasings collected in the staff workshop.

## What each piece needs from people before launch

- **IT:** the Lusaka VM (2 vCPU, 4 GB, 40 GB), a public HTTPS address, a
  TLS certificate, outbound access to Meta and to the model download site,
  a backup location inside Zambia, and a second VM for Chatwoot.
- **Product owner:** create the Teams Workflow and hand over its address;
  make the decisions below; lead Meta onboarding; confirm the public
  WhatsApp number; run the weekly shadow reviews before switching on hybrid
  mode; sign the go/no-go checklist.
- **Legal, Compliance and the DPO:** sign off every answer and message in
  [intent-review.md](intent-review.md) (regenerated today, including the
  new consent, opt-out and feedback wording); rule on consent and opt-out
  rules, retention periods, and whether sending tickets to Jira in the cloud
  is a cross-border transfer; complete the DPIA.
- **Contact-centre lead:** review the notes agents see in Chatwoot; train
  agents; name pilot roles.
- **Marketing:** launch communications (from
  [marketing-launch-kit.md](marketing-launch-kit.md), a draft for Legal);
  name an owner for honouring opt-outs; set campaign codes.
- **Content owner and staff:** the phrase workshop, and native speakers to
  check the draft Bemba and Nyanja phrases.

## Top decisions to confirm

1. **Launch in hybrid mode?** Recommended once shadow mode has run on real
   traffic and at least one weekly review agrees, even though it is just
   short of two targets.
2. **Real Jira only after a Legal ruling** on cross-border transfer, since
   tickets carry names and phone numbers. Until then Jira stays in mock
   mode.
3. **Teams alert timing:** after a "Resolved" post, a returning outage can
   wait up to 15 minutes before it is posted again. Repost Sev 1 at once, or
   keep the one-post-per-15-minutes rule?
4. **Urgent messages while an agent has the conversation** are only passed
   to the agent; they do not start the fraud flow. Acceptable?
5. **Marketing consent:** is a typed "sure" a valid yes, and should "No" be
   the first button?
6. **Server settings file** permissions: settled as root-only (mode 600);
   the alert job reads it through `deploy/admin.sh`. No action needed.
7. **Background Jira sending** can lose an issue if the server restarts at
   that moment (the ticket itself is safe). Add a retry queue before real
   Jira goes live?

The full list of 26 open concerns, with owners, is in
[remaining-work-plan.md](remaining-work-plan.md) ("Update 24/09/2026").
The decisions made during the build are in the appendix below, for the
decisions log.

## Open risks

- **Server not yet provisioned.** Every live test (load, deploy, backup
  restore, alerts) waits on it.
- **Targets not yet met** for understanding (see above).
- **WhatsApp coexistence** (the bot pausing when staff reply from the
  WhatsApp Business app) is being built now and is needed before the staff
  pilot.
- **WhatsApp sending is one message at a time**, about 1.6 messages a
  second. Fine for a pilot; needs a decision before volume grows.
- **Unverified outside facts** marked [VERIFY] or [CONFIRM] in the code and
  documents: Meta prices and screens, the Chatwoot version's behaviour,
  Jira endpoints, contact numbers, retention periods.
- **Reviewer fixes done since:** the feedback question keeps "Talk to a
  person", "Request a callback" always opens the callback form (so consent
  and campaign are captured on every channel), emails are masked before
  anything reaches Chatwoot, failed-message records keep no customer text,
  a bad database or setting can't stop start-up, the alert and weekly jobs
  are in the server schedule, and the env file stays root-only (mode 600).

## Where to read more

- Status and remaining work by owner: [remaining-work-plan.md](remaining-work-plan.md)
- Ticket status: [execution-plan.md](execution-plan.md), Appendix A
- Running the server: [runbook-production.md](runbook-production.md)
- Incidents, alerts and kill switches: [runbook-incidents.md](runbook-incidents.md)
- Agent desk: [chatwoot-setup.md](chatwoot-setup.md)
- Load test: [load-test-results.md](load-test-results.md)
- Marketing: [marketing-launch-kit.md](marketing-launch-kit.md)
- Launch: [go-no-go.md](go-no-go.md), [pilot-runbook-whatsapp.md](pilot-runbook-whatsapp.md),
  [hosting-requirements-it.md](hosting-requirements-it.md), [meta-onboarding-guide.md](meta-onboarding-guide.md)
- Legal and Compliance: [legal-compliance-pack.md](legal-compliance-pack.md), [dpia-draft.md](dpia-draft.md)
- Workshop: [phrase-workshop-kit.md](phrase-workshop-kit.md)
- Every decision to approve or reverse: [decisions-log.md](decisions-log.md)

## Appendix: decisions made by the build streams

For `decisions-log.md`, section "Decisions added by the build streams".
Every row is **Proposed** until the product owner approves or reverses it.

| # | Decision | Why | How to reverse |
|---|---|---|---|
| B1 | Alerts go to a Teams group chat (Power Automate Workflow webhook) and to Jira (label `chatbot-alert`, Highest for Sev 1, High for Sev 2). Teams: one post per issue per 15 minutes plus a "Resolved" post; Jira: one issue per 24 h, never closed by the script. | Follows the PO's 15-minute ceiling; Jira is the lasting record; people close issues. | Unset `ALERT_TEAMS_WEBHOOK_URL` (mock mode); change `ALERT_TEAMS_REPEAT_MINUTES` / `ALERT_JIRA_REPEAT_HOURS`. |
| B2 | The alert job reads `/health` from outside the app and declares it down only after 3 failed tries 10 s apart. | Only an outside process can see "down"; a deploy restart must not raise a Sev 1. | Change the retry constants in `admin/alerts.py`. |
| B3 | Sev 1 = bot down, broken `flags.json`, or an unrouted message that reads as fraud. Everything else Sev 2; no automatic Sev 3. | Follows the R1 severity table. | Edit the severity map in `admin/alerts.py`. |
| B4 | New `flags_file` check: `flags.json` must parse and hold only `true`/`false`. | A quoted "false" silently leaves a kill switch on. | Remove the check from `app/health.py`. |
| B5 | `/health` stays public and HTTP 200 when a check fails (503 only if a store is unreadable); it shows counts only. | Outside uptime checkers need it. | Limit `/health` detail to internal addresses in nginx. |
| B6 | Retention purges run in the app at start-up and nightly at 02:00 Lusaka, and now include the webhook inbox. | There was no scheduled purge and the inbox was never purged. | Set `PURGE_HOUR`; retention days are env settings. |
| B7 | Env file `/etc/abz-chatbot/env` stays root-only, mode 600; the alert cron runs as root through `deploy/admin.sh`, which runs the script as the service user. | Keeps secrets root-only; matches `deploy/lib.sh`. | Change `check_env` in `deploy/lib.sh` and the runbooks. |
| B8 | Deploys accept only `vX.Y.Z` tags, test each release in its own environment on scratch data before switching, and switch back if `/health` fails. Rollback takes a release name, never a path. | Only a reviewed release can go live; a broken one never serves traffic. | Edit `deploy/deploy.sh` / `rollback.sh`. |
| B9 | Data and kill switches live outside the release (`ABZ_DATA_DIR`, `ABZ_FLAGS_FILE`). | They must survive a deploy or rollback. | Unset both: the repo's `data/` and `flags.json` are used. |
| B10 | `REPLY_KEY` can hold several keys (first is primary); `admin.rotate_reply_key` re-encrypts. | Rotation with no downtime. | Use a single key. |
| B11 | A real Jira push runs in a background thread; mock mode stays inline. | Inline, a slow Jira raised website p95 from 19 ms to 322 ms. | Revert in `app/audit.py`. A retry queue is still an open decision. |
| B12 | The WhatsApp send worker stays single. | Parallel sending changes ordering and rate limits; out of scope now. | A design change, recorded in `load-test-results.md`. |
| B13 | Feedback is asked of a fixed 20% of customers (by hashed id), once per session, never in a session with a fraud report; three buttons (Good, Not good, Main menu). | Stable, testable, adjustable without a restart; three buttons stay as WhatsApp buttons. | `CSAT_SAMPLE_RATE=0` stops it. |
| B14 | The weekly report writes `data/report.md`, shows n/a rather than a false PASS, and gives the WhatsApp cost in US$ only, never converted. | Honest when data is missing; no mixed currencies. | `--stdout` prints as before. |
| B15 | Only WhatsApp uses Chatwoot; Messenger keeps the Page Inbox, the website keeps tickets and callbacks. Chatwoot is on only when all four settings are set. | M4 already works; a half-configured desk must not receive handoffs. | `CHATWOOT_ENABLED=false`, or unset the settings. |
| B16 | Everything sent to Chatwoot is masked again and phone numbers are redacted; the contact is identified by the hashed id only. If the desk fails, the bot does not pause and Jira stays the record. | No phone number reaches the desk; the customer is never left with nobody. | Code change in `app/desk/bridge.py`. |
| B17 | The Chatwoot webhook uses a long secret in the URL path (403 if wrong, 404 when off); an agent reply extends the pause by 24 h. | Chatwoot webhooks carry no signature [VERIFY]; a silent desk hands the customer back to the bot. | Change `DESK_IDLE_HOURS`; the path secret needs a code change. |
| B18 | Negated requests ("I don't want a loan") are dropped before scoring, in both modes; past tense and "not sure" are kept. | Deterministic, measured neutral in the live mode; the fix blocked hybrid mode. | Code change in `app/matcher.py`. |
| B19 | Thresholds from the calibration split only: `EMB_HIGH` 0.715, `EMB_MEDIUM` 0.435; 25 draft phrases removed that raised wrong or off-topic answers. Hybrid mode stays off. | Never tune on the test set; gates never loosen. | `EMB_*` env settings; `EMBEDDINGS_ENABLED`. |
| B20 | Marketing consent is an optional fifth step of the callback, asked by default, never assumed: tickets record yes, no or not asked; Jira label only on yes; opt-out overrides earlier consent. | ECT Act opt-in principle [VERIFY with Legal]; Marketing and Legal can tell "declined" from "never asked". | `MARKETING_CONSENT_ENABLED=false`. |
| B21 | Opt-out commands are exact whole messages ("unsubscribe", "opt out", "stop offers"…); the bare word "stop" still cancels. | "unsubscribe my card" must not become an opt-out. | Edit the list in `app/router.py`. |
| B22 | Campaign source: sanitised, no long digit runs, first touch wins, logged as a separate `session_source` event; WhatsApp `ref:` token stripped before routing. No bulk lead export. | A code can never carry PII; campaigns measured without personal data leaving Jira. | Code change in `app/campaign.py`. |
| B23 | "Request a callback" added to the two account answers that lacked it, so every product answer reaches the callback flow in one tap. | Main entry points for account leads. | Edit `knowledge/intents/accounts.yaml`. |
| B24 | Go/no-go is signed in the commit the release tag points to; safety rows can never be waived; Jira hosting is its own legal question; staff pilot fraud tests start with "TEST". | Ties the signature to the exact code deployed; safety is non-negotiable. | Edit `go-no-go.md` and the pilot runbook. |
