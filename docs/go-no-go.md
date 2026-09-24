# Go/no-go checklists (ticket R2)

> **Draft for the product owner, Legal and Compliance to review.** Written
> 24/09/2026. Nothing here is approved until the PO accepts this file. The
> criteria come from `execution-plan.md` §11 (R2) and `remaining-work-plan.md`
> §3 (R2); the targets come from `excellence-plan.md` §1.

One table per milestone. A milestone is **go** only when every row is
**Done** and signed. A row that can't be met is either fixed or explicitly
waived by the PO and the row's owner, with the reason written in the Status
cell ("Waived: …"). Safety rows (marked **S**) can never be waived.

Status values: `Not started`, `In progress`, `Done`, `Waived: <reason>`.

## How a checklist is signed

1. The PO copies the milestone's table into the release pull request (or,
   while work lands directly on `master`, into the commit that the release
   tag will point to) and fills in the **Evidence** and **Status** columns.
2. Each owner checks their rows and adds their name and the date
   (DD/MM/YYYY) in **Signed by / date**. Named people, never a team.
3. When every row is signed, the PO commits the filled-in `docs/go-no-go.md`
   and tags that commit with an annotated tag, for example:
   `git tag -a v1.0-m3 -m "M3 go/no-go signed: docs/go-no-go.md at this commit"`.
   The tag is what `deploy/deploy.sh` fetches (P7), so the production code and
   the signed checklist are the same commit.
4. Git history is the record. Never edit a signed table afterwards; a later
   change goes in a new commit with a new date.

A **no-go** is recorded the same way (Status and a one-line reason), without
a tag. The milestone moves to the next date in `execution-plan.md` §12.

Owners: **PO** product owner · **Dev** developer · **CO** content owner ·
**Legal** Legal/DPO · **Comp** Compliance/IT risk · **CC** contact-centre lead ·
**SM** social-media team · **Ops** Operations/Risk · **Mkt** Marketing ·
**IT** the bank's IT (hosting).

---

## M3 · Website live (soft launch) — target W11 (07/12/2026)

| # | Criterion | Evidence (file / command / link) | Owner | Status | Signed by / date |
|---|---|---|---|---|---|
| 3.1 | Every `[CONFIRM` placeholder resolved (K2) | `python -m admin.legal_export` lists none; search for `[CONFIRM` in `app/` and `knowledge/` returns nothing | CO + Ops | Not started | |
| 3.2 | Legal sign-off of `docs/intent-review.md`: every intent answer, system message, utility template and channel variant; every entry `status: approved` | Regenerated `docs/intent-review.md` at the release commit; Legal's written approval (email or memo reference) | Legal | Not started | |
| 3.3 | Every `[VERIFY]` item in code that affects the website resolved | `remaining-work-plan.md` §3 K2 list | Dev | Not started | |
| 3.4 | P7 accepted: production VM in Zambia; two deploys and two rollbacks done; one backup restored | `docs/runbook-production.md` acceptance log; `docs/hosting-requirements-it.md` | Dev + IT | Not started | |
| 3.5 | `/health` green from outside the bank network over HTTPS with a valid certificate | `curl https://<production host>/health` from an outside connection; uptime-check link | Dev | Not started | |
| 3.6 | L1 DPIA completed and signed by the DPO | `docs/dpia-draft.md` → final DPIA reference | Legal (DPO) | Not started | |
| 3.7 | L3 privacy notice and first-contact wording approved and live on abbank.co.zm | Privacy-policy URL; the `welcome` / `disclosure` entries approved in `knowledge/system_messages.yaml` | Legal + CO | Not started | |
| 3.8 | L4 Bank of Zambia cyber / IT-risk engagement complete (hosting, third parties, whether notification is needed) | Compliance memo reference | Comp | Not started | |
| 3.9 | L8 ODPC registration covers chatbot processing and lists the processors | DPO confirmation | Legal (DPO) | Not started | |
| 3.10 | L5 retention periods decided and set (replacing the placeholders) | `TRANSCRIPT_RETENTION_DAYS`, `TICKET_RETENTION_DAYS` in the production env file match Legal's ruling | Legal + Dev | Not started | |
| 3.11 | Jira destination decided: Legal has ruled on where tickets may be held (see `legal-compliance-pack.md` §2.9) and `JIRA_*` is set, or Jira stays off | Env file; Legal note | Legal + CC | Not started | |
| 3.12 | R1 live: `docs/runbook-incidents.md` agreed; alerts reach the Teams group chat **and** open a Jira ticket; one test alert of each received | Screenshot of the test alert in Teams; the test Jira key | Dev + CC | Not started | |
| 3.13 | Kill switches rehearsed by the PO and CC lead (`FREE_TEXT_ENABLED`, `WIDGET_ENABLED`) on staging | Runbook rehearsal note with date | PO + CC | Not started | |
| 3.14 **S** | Red-team fraud, theft and lost-card phrasings reach the fraud flow: **100%** | `python -m pytest tests/test_redteam.py tests/test_redteam_routing.py tests/test_urgent.py -q` | Dev | Not started | |
| 3.15 **S** | Everyday messages wrongly sent into fraud or complaint without a confirmation question: **0** on the negative set | `tests/data/urgent_negative.txt` via `tests/test_urgent.py` | Dev | Not started | |
| 3.16 **S** | Fraud reports that include a way to reach the customer (or an explicit skip): **100%** | `tests/test_flows.py` (fraud `contact` step) | Dev | Not started | |
| 3.17 **S** | Out-of-scope questions answered directly: **≤ 3%** on the held-out and out-of-scope sets | `python -m admin.eval_report`; `tests/test_eval_gates.py` | Dev | Not started | |
| 3.18 **S** | Unmasked PII reaching storage or a model: **0%** | `tests/test_guards.py`, `tests/test_audit_identity.py`; a manual check of `data/audit.jsonl` from the staff trial | Dev + Comp | Not started | |
| 3.19 **S** | Customer-facing text that isn't approved wording: **0%** | AST test in `tests/test_messages.py`; row 3.2 | Dev + CO | Not started | |
| 3.20 | Full suite green at the release commit | `python -m pytest -q` output pasted into the release PR | Dev | Not started | |
| 3.21 | `ADMIN_USER` and `ADMIN_PASSWORD` set (long random password), shared only with named CC leads | Env file (value not recorded here); list of named holders | Dev + CC | Not started | |
| 3.22 | `USER_KEY_SECRET` and `REPLY_KEY` set in the production env file **and** that file backed up inside Zambia (two named people can retrieve it) | `deploy/backup.sh` run log; the password-manager entry name | Dev + IT | Not started | |
| 3.23 | `ALLOWED_ORIGINS` is the bank's domain only; `PROXY_HOPS` matches the proxy chain | Env file; a browser test from abbank.co.zm | Dev | Not started | |
| 3.24 | Load test on production: p95 ≤ 150 ms server-side, no memory growth (P9) | `docs/load-test-results.md` | Dev | Not started | |
| 3.25 | Out-of-hours fraud route decided (O1) and the emergency number in every fraud message is real | `ABZ_EMERGENCY_PHONE` set; Ops confirmation | Ops | Not started | |
| 3.26 | "Continue on WhatsApp" link on the website is **off** | Widget config on the production page | Dev | Not started | |
| 3.27 | Holiday change-freeze respected (O2) | Release date against the freeze window | PO | Not started | |

**Go decision (M3):** ☐ Go ☐ No-go · PO: __________ · Date: __/__/____

---

## M4 · WhatsApp pilot — staff from W15 (04/01/2027), limited public from W17 (18/01/2027)

Everything in M3 still holds (re-check rows 3.1, 3.2, 3.12 and 3.14–3.20 at
this release), plus:

| # | Criterion | Evidence (file / command / link) | Owner | Status | Signed by / date |
|---|---|---|---|---|---|
| 4.1 | M3 checklist signed | Tag `v1.0-m3` (or later) | PO | Not started | |
| 4.2 | **L2** legal ruling on DPA s.70/71 (Meta processing outside Zambia): lawful basis recorded; any ODPC authorisation or approved contract in place | Legal memo reference | Legal | Not started | |
| 4.3 | L3 privacy notice covers WhatsApp; first-contact wording approved for WhatsApp | Privacy-policy URL; approved `welcome` channel variant | Legal + CO | Not started | |
| 4.4 | **W1** complete: bank-owned Meta Business portfolio with ≥ 2 bank admins; business verified; System User token in the password manager; production number registered, display name approved, 2FA PIN set, payment method added | `docs/meta-onboarding-guide.md` checklist, all rows done | PO | Not started | |
| 4.5 | Number decision recorded (coexistence for the pilot, then migration; see `decisions-log.md`) | Decisions log row signed | PO + Mkt + CC | Not started | |
| 4.6 | W2–W8 done and tested against Meta's test number on staging | Appendix A of `execution-plan.md`; staging demo note | Dev | Not started | |
| 4.7 | The three utility templates (`case_received`, `case_update`, `callback_scheduled`) approved by Legal (L6) **and** by Meta, under the same names as `knowledge/templates.yaml` | WhatsApp Manager template status screenshot | Legal + PO | Not started | |
| 4.8 | `WA_*` secrets set in the production env file only; webhook subscribed; signature check passing | `/health`; a signed test message from the test number | Dev | Not started | |
| 4.9 | `WA_GRAPH_VERSION` and the BSUID field names checked against Meta's current docs **[VERIFY]** | Dev note with date | Dev | Not started | |
| 4.10 | Handoff owner, hours and SLA agreed for WhatsApp (O1; coexistence means staff reply from the Business app during the pilot) | CC memo | CC | Not started | |
| 4.11 | Kill switch `WHATSAPP_ENABLED=false` rehearsed on staging: one static reply, never silence | Rehearsal note | PO + CC | Not started | |
| 4.12 | Meta webhook-failure emails go to a shared inbox watched by the CC lead | Inbox name | Dev + CC | Not started | |
| 4.13 | **Staff pilot go/no-go passed** (`docs/pilot-runbook-whatsapp.md` §5, stage 1): §1 targets on pilot data, no Sev 1 in the last 7 days, handoff SLA ≥ 95% | Final staff-pilot triage note; `python -m admin.report --days 14` | PO + CC | Not started | |
| 4.14 | For the **public** stage only: branch QR codes printed and the website "Continue on WhatsApp" link ready to switch on; no mass marketing | MK1 note | Mkt | Not started | |
| 4.15 | Budget for WhatsApp message fees approved (rate from Meta's current rate card **[VERIFY]**) | Finance approval reference | PO | Not started | |

**Go decision (M4 staff pilot):** ☐ Go ☐ No-go · PO: __________ · Date: __/__/____

**Go decision (M4 public pilot):** ☐ Go ☐ No-go · PO: __________ · Date: __/__/____

---

## M5 · Messenger live — target W18 (25/01/2027)

| # | Criterion | Evidence (file / command / link) | Owner | Status | Signed by / date |
|---|---|---|---|---|---|
| 5.1 | M3 checklist signed; L2 ruling covers Messenger as well as WhatsApp | Tag; Legal memo | PO + Legal | Not started | |
| 5.2 | Privacy policy covers Messenger (the items in `messenger-app-review.md` §4) | Privacy-policy URL | Legal | Not started | |
| 5.3 | **Meta App Review passed** for the permissions in `messenger-app-review.md` §1 (M1 pack) | App Review approval screenshot and date | PO | Not started | |
| 5.4 | `MS_*` secrets set; webhook subscribed; `python -m admin.messenger_profile --apply` run (Get Started, greeting, menu, ice breakers) | Command output | Dev | Not started | |
| 5.5 | **Page Inbox handover tested with the social team**: "Talk to a person" passes the thread; the bot stays silent while staff reply; "Done" hands it back | Test log with the SM lead's name | SM + Dev | Not started | |
| 5.6 | `PAGE_INBOX_APP_ID` and the handover/standby behaviour checked against Meta's current docs **[VERIFY]** | Dev note | Dev | Not started | |
| 5.7 | Social team's hours and SLA for Page Inbox handoffs agreed | SM memo | SM + CC | Not started | |
| 5.8 | `MESSENGER_PUBLIC_REPLIES` stays **off** unless comms-approved public wording exists and the PO turns it on | `flags.json` | PO | Not started | |
| 5.9 | Kill switch `MESSENGER_ENABLED=false` rehearsed on staging | Rehearsal note | PO + SM | Not started | |

**Go decision (M5):** ☐ Go ☐ No-go · PO: __________ · Date: __/__/____

---

## M6 · Full launch — target W22 (22–26/02/2027)

| # | Criterion | Evidence (file / command / link) | Owner | Status | Signed by / date |
|---|---|---|---|---|---|
| 6.1 | M3, M4 (public stage) and M5 signed | Tags | PO | Not started | |
| 6.2 | **H2 live**: Chatwoot on a second VM in Zambia, API-channel inbox, round trip tested (handoff, forwarded messages, agent reply, 24-h refusal, resolve resumes the bot) | H2 test run; `/health` | Dev + IT | Not started | |
| 6.3 | Chatwoot edition's licence confirmed (Community edition) **[VERIFY]** | Licence note | Dev + Legal | Not started | |
| 6.4 | **Agents trained** on Chatwoot, the 24-h window and the `case_update` template | Training attendance list (names held by CC, not in git) | CC | Not started | |
| 6.5 | **§1 targets met on 2 consecutive weeks of real traffic, per channel** (web, WhatsApp, Messenger): right ≥ 85%, wrong ≤ 2%, out of scope ≤ 3%, ≤ 4 bot messages per conversation, delivery failures ≤ 1%, CSAT ≥ 4.2, handoff SLA ≥ 95%, p95 ≤ 150 ms | Two weekly `data/report.md` files (H6), attached to the status notes | PO + Dev | Not started | |
| 6.6 | The safety rows 3.14–3.19 still pass at the release commit | `python -m pytest -q` | Dev | Not started | |
| 6.7 | Hybrid matcher decision taken (on or off) with its shadow reviews recorded | `admin.shadow_report` reviews; `flags.json` | Dev + CO | Not started | |
| 6.8 | WhatsApp number fully migrated to the Cloud API (option A), if the PO keeps that decision; Official Business Account applied for | Decisions log; WhatsApp Manager | PO + Mkt | Not started | |
| 6.9 | **MK1 ready**: official WhatsApp number published everywhere, anti-scam messaging, branch QR codes, launch communications approved | Marketing sign-off | Mkt + Legal | Not started | |
| 6.10 | Weekly quality rhythm running: report reviewed each week, `bot-wrong` loop (H4) feeding labelling | Last two status notes | PO + CC | Not started | |
| 6.11 | Any marketing use of leads matches Legal's ruling on consent (`legal-compliance-pack.md` §3) | Legal note | Legal + Mkt | Not started | |

**Go decision (M6):** ☐ Go ☐ No-go · PO: __________ · Date: __/__/____
