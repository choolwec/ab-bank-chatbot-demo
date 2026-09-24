# DPIA draft: AB Bank customer assistant (ticket L1, starter)

> **Draft for the Data Protection Officer.** Pre-filled by the project on
> 24/09/2026 from the code (commit `8e97aa5` and this week's build) so the
> DPO starts from facts, not a blank form. It is not a completed DPIA: the
> lawful basis, necessity and proportionality judgements, and the risk
> ratings are the DPO's to make. Legal citations must be confirmed against
> the official text. Items marked **[DPO]** need a decision;
> **[CONFIRM]** needs a fact from the bank; **[VERIFY]** needs checking
> with an external party.

## 1. Summary

The assistant is a rule-based chatbot on the bank's website, WhatsApp and
Facebook Messenger. It answers general questions from approved wording,
finds branches, and takes fraud reports, complaints and callback requests,
which become tickets for staff. It has **no access to accounts** and uses
**no generative AI**. The main privacy risks are: customers volunteering
sensitive details in free text; Meta (and possibly Atlassian) processing
data outside Zambia; and staff tickets holding names and contact numbers.

## 2. Description of the processing

### 2.1 Channels and who the data subjects are

| Channel | Data subjects | How they are identified to the bot |
|---|---|---|
| Website widget | Visitors to abbank.co.zm (customers and non-customers) | A random session id created by the server, kept in the browser's `sessionStorage` for that tab; no cookies (`widget/widget.js`) |
| WhatsApp | Anyone who messages the bank's WhatsApp number | Meta's business-scoped user id (BSUID) when sent, else the WhatsApp id, which is the phone number (`app/channels/whatsapp.py`) |
| Messenger | Anyone who messages the bank's Facebook Page, or comments on its posts with urgent wording | The page-scoped id (PSID) (`app/channels/messenger.py`) |
| Staff | Contact-centre and social-media agents, admins | Admin username (HTTP Basic auth); agents' own Jira/Chatwoot logins |

### 2.2 Data inventory

**Every message, every channel:**

| Data | Where stored | Notes |
|---|---|---|
| Message text, **masked** | Audit log (`data/audit.db` + `audit.jsonl`), session transcript (`data/sessions.db`) | `app/guards.py` masks card-shaped numbers (13–19 digits), NRC numbers, account numbers stated as such, and PINs, passwords and OTPs **before** anything is stored or matched. Phone numbers (≤ 12 digits) and email addresses are **not** masked, because the flows need them |
| Bot replies | Audit log, session transcript | Approved wording only |
| Intent, confidence, action | Audit log | For quality reports |
| Session id (random), channel, `user_hash` | Audit log, tickets | `user_hash` = HMAC-SHA256 of `channel:user_key` with a secret key (`app/identity.py`). The raw phone number, BSUID or PSID is never logged |
| Session state | `data/sessions.db` | Row key is the **hashed** user key; state holds flow answers in progress, the masked transcript (up to 200 turns), and sealed references |
| Sealed reply address | Session, ticket `reply_to`, inbox (until processed) | The raw platform id, **encrypted** with `REPLY_KEY` (Fernet), so staff can reply later. Cleared from the inbox row once processed |
| IP address (web) | Rate limiter, **in memory only**; nginx access logs on the VM | Not in the audit log. nginx log retention is set by logrotate **[DPO: confirm the period]** |

**Per flow (from `app/flows/*`):**

| Flow | Fields collected | Result |
|---|---|---|
| Fraud / lost card (`fraud.py`) | What happened (free text), when, which service (card, eTumba, …), a contact (phone, email, or an explicit "skip"). Extracted hints: date, branch, amount | Ticket `FRD-…`, urgent; never closed by the bot |
| Complaint (`complaint.py`) | Topic, details (free text), contact (phone, email or skip); confirmed by the customer before sending | Ticket `CMP-…` to the complaints team |
| Callback / "talk to a person" (`lead.py`) | Name, phone, topic, preferred time (morning/afternoon); confirmed before sending. Plus a yes/no marketing-consent answer with its timestamp (MK2; `MARKETING_CONSENT_ENABLED`) and the campaign source (MK3) | Ticket `CBK-…`; a person calls within a working day |
| Handoff to an inbox (Messenger, and WhatsApp once Chatwoot exists) | No extra fields; the conversation so far | Ticket `HND-…`; the thread passes to staff |
| Branch / agent locator (`locator.py`) | Town chosen from buttons; on WhatsApp, optionally a **shared location** | The location is used once to find the nearest branches and is **never logged** (`[location shared]` is stored instead) |
| One-tap satisfaction (H5, this week's build) | Thumbs up or down, sampled on about 20% of resolved conversations, never after fraud | Audit event |

**Not collected:** photos, documents, videos and voice notes are **not
downloaded or stored**; the customer is asked to type instead
(`app/channels/messaging.py`). A caption typed with a photo is treated as
text and masked. WhatsApp and Messenger profile names are not stored
[VERIFY against the final parsing code].

**Tickets** hold the flow fields above (so a **name and phone number or
email in clear**), the full masked transcript, the channel and a minimised
`reply_to` (channel, `user_hash`, sealed address, when the 24-hour window
closes).

### 2.3 Purposes

1. Answering customers' general questions.
2. Taking and routing fraud and lost-card reports urgently.
3. Taking complaints (BoZ complaints-handling duties).
4. Arranging callbacks and handoffs to staff.
5. Service quality: weekly reports, labelling of masked messages to improve
   understanding (N1), satisfaction sampling.
6. Security and abuse prevention: rate limits, abuse detection, audit.
7. **Proposed:** marketing follow-up of callback customers who explicitly
   consent (see `legal-compliance-pack.md` §3). **[DPO]**

### 2.4 Lawful basis

| Purpose | Lawful basis | Notes |
|---|---|---|
| 1–4 | **[DPO to decide]** | |
| 5 | **[DPO to decide]** | Uses masked text only |
| 6 | **[DPO to decide]** | |
| 7 | **[DPO to decide]**; project assumes explicit consent | ECT Act opt-in/opt-out |
| Transfers to Meta (and Atlassian, if used) outside Zambia | **[DPO / Legal, L2]** | DPA s.70/71 |

## 3. Data flows

```
 Customer
   │  website widget (HTTPS)        WhatsApp / Messenger app
   │                                   │
   │                                   ▼
   │                        Meta platform (outside Zambia [VERIFY];
   │                        decrypts and holds messages up to 30 days)
   │                                   │ signed webhook (HTTPS)
   ▼                                   ▼
 ┌──────────────────── Bank VM in Zambia (P7) ─────────────────────┐
 │ nginx (TLS) ─► app: guards.mask() FIRST ─► router / flows        │
 │                     │                                            │
 │   inbox.db (masked text, sealed id) ─► worker ─► reply via Meta  │
 │   sessions.db (hashed key, masked transcript, sealed refs)       │
 │   audit.db / audit.jsonl (masked text, user_hash)                │
 │   tickets (name, contact, masked transcript, sealed reply_to)    │
 │   nightly backup ─► second location in Zambia                    │
 └───────────┬───────────────────────────────┬──────────────────────┘
             │ ticket copy (HTTPS)           │ handoff (H2, HTTPS)
             ▼                               ▼
   Contact-centre Jira                Chatwoot, second VM in Zambia
   (Atlassian Cloud? outside          (contact = user_hash; masked
    Zambia [CONFIRM], see §4)          transcript as a private note)
             │                               │
             ▼                               ▼
        Staff (fraud team, complaints, contact centre, social team)
```

The admin pages (`/admin/*`: ticket preview, cases, template sending) are
behind HTTP Basic auth and return 404 until credentials are set.

## 4. Processors and recipients

| Party | Role [DPO to confirm] | Location | What it receives | Status |
|---|---|---|---|---|
| Hosting (bank IT, or a Lusaka data centre: Paratus, Infratel or MTN) | Processor if external | Zambia | Everything on the VM | Decision pending (`hosting-requirements-it.md`) |
| Meta Platforms (WhatsApp, Messenger) | Processor (research view) **[DPO/Legal, L2]** | Outside Zambia [VERIFY] | Every WhatsApp/Messenger message in both directions, platform ids, phone numbers (WhatsApp) | Needs L2 ruling |
| Atlassian (Jira), if Cloud | Processor | **Outside Zambia** if Atlassian Cloud [CONFIRM which Jira; VERIFY Atlassian's data-residency options] | Ticket reference, channel, the flow's fields (name, contact in clear), the last 40 masked transcript turns, the reply-window closing time (`app/jira_export.py`). Not the `user_hash` or the sealed address | Mock mode today; **cross-border question for Legal** (`legal-compliance-pack.md` §2.9) |
| Chatwoot (self-hosted, Community edition) | Software run by the bank; no vendor access | Zambia | `user_hash`, name if given, masked transcript, forwarded masked messages | Planned (H2) |
| Render (staging) | Processor | Outside Zambia | **Synthetic data only**; staff told not to use real data | In use for demos |
| Model files (Hugging Face download) | Not a recipient | — | Nothing: the model is downloaded once and runs locally | — |

## 5. Retention

Current values are **placeholders pending Legal (L5)**, from `app/config.py`:

| Data | Current setting | Mechanism |
|---|---|---|
| Audit events | 90 days (`TRANSCRIPT_RETENTION_DAYS`) | `audit.purge_expired()` |
| Sessions | 90 days since last activity (same setting) | `store.purge_expired()` |
| Tickets | **Never auto-deleted** (`TICKET_RETENTION_DAYS = 0`) | Follows the complaints unit's policy **[DPO]** |
| Inbox rows (WhatsApp/Messenger) | Purged at start-up and nightly (R1, `app/housekeeping.py`) | `inbox.purge()` |
| Backups | 14 days (plan, P7) | `deploy/backup.sh` |
| Jira copies | Jira's own settings **[CONFIRM]** | Outside the app |
| Meta | Up to 30 days (research) [VERIFY] | Outside the bank's control |
| nginx logs | logrotate setting **[DPO]** | On the VM |
| Evaluation / labelling sets | Masked, de-duplicated, second PII filter (`admin/export_utterances.py`); kept in git **[DPO: acceptable?]** | Manual |

## 6. Security controls

| Control | Where | What it does |
|---|---|---|
| PII masking before anything else | `app/guards.py`; invariant in `CLAUDE.md` | Card, NRC, account and credential numbers masked before matching, flows, logs, tickets, Jira and reports. Tested in `tests/test_guards.py` and the red-team suites |
| Hashed identities | `app/identity.py` | Only `user_hash` (HMAC-SHA256, secret key) in logs and reports; sessions keyed by hash |
| Sealed reply addresses | `app/identity.py` (Fernet, `REPLY_KEY`) | The raw platform id is stored only encrypted; the key lives in the env file |
| Secrets outside git | `app/config.py`, P7 env file (root-only) | Meta tokens, Jira token, admin password, keys; backed up to the password manager |
| Admin authentication | `app/adminauth.py`, P8 | HTTP Basic auth on every `/admin/*` route; 404 when unset; tested for every admin route |
| Webhook signatures | `app/channels/whatsapp.py`, `messenger.py` | HMAC-SHA256 of the raw body checked on every Meta request; failures rejected |
| Rate limits | `app/ratelimit.py`; per customer on Meta channels | Limits abuse and cost |
| No media stored | `app/channels/messaging.py` | Photos of cards or NRCs can't be masked, so none are accepted |
| No account access, no generative AI | Architecture | The bot can't disclose account data or invent answers; all wording is approved |
| Human takeover pauses the bot | Messenger handover; Chatwoot (H2) | No bot replies while a person is handling the chat |
| Kill switches | `flags.json`, env vars | Channel, free text, models: off without a restart |
| Tickets closed only by people | Flows; invariant | The bot never marks a fraud or complaint resolved |
| Hosting in Zambia, TLS, inbound 443 only | P7, `hosting-requirements-it.md` | |
| Audit trail | `app/audit.py`, git history for wording | Every reply and wording change traceable |

## 7. Risks and mitigations

Likelihood and severity are **for the DPO to rate**; the project's
suggestions are in brackets.

| # | Risk | Mitigations in place | Remaining actions | Likelihood | Severity |
|---|---|---|---|---|---|
| R1 | Customer types a card, NRC, account number or PIN | Masking before storage; the bot warns and never asks for them | Keep the red-team suite growing; check the staff-trial logs | [DPO] (likely) | [DPO] (high) |
| R2 | Customer sends a photo of a card or NRC | Not downloaded or stored; asked to type instead | Meta still receives it (L2) | [DPO] | [DPO] |
| R3 | Meta processes messages outside Zambia | Customer-initiated only; disclosure; minimal data | L2 ruling; privacy notice (L3) | [DPO] (certain) | [DPO] |
| R4 | Ticket data (names, numbers) in Atlassian Cloud outside Zambia | Jira in mock mode until decided; masked transcripts | Legal ruling (§2.9 of the pack); reduced field set or in-country Jira | [DPO] | [DPO] |
| R5 | Unmasked data in free-text fields reaches tickets or Jira (for example a phone number in "what happened") | Masking covers card/NRC/account/PIN; phone numbers are by design not masked | [DPO] accept, or mask phone numbers outside contact fields | [DPO] | [DPO] |
| R6 | Loss or leak of `REPLY_KEY` / `USER_KEY_SECRET` | Env file root-only; backed up in the password manager; rotation procedure (P7) | Named key holders | [DPO] | [DPO] |
| R7 | Admin pages exposed | Basic auth; 404 when unset; long random password | IP restriction to the bank network [DPO: required?] | [DPO] | [DPO] |
| R8 | Wrong customer receives a reply | Replies addressed by sealed id; sessions keyed per customer; tested | Pilot triage (Sev 1) | [DPO] | [DPO] |
| R9 | Marketing use beyond consent | Explicit yes/no; opt-out commands; no bulk export; Jira label only | Legal ruling (pack §3) | [DPO] | [DPO] |
| R10 | Retention longer than needed (tickets never purged) | Placeholders documented | L5 decision | [DPO] | [DPO] |
| R11 | Automated decisions affecting customers | None: the bot routes and informs; no credit or account decisions | Keep it that way | [DPO] (low) | [DPO] |
| R12 | Scammers impersonate the bank on WhatsApp | One official number; blue badge (after migration); templates without links | MK1 anti-scam messaging | [DPO] | [DPO] |
| R13 | Staff use real customer data on staging (Render, outside Zambia) | Staff told synthetic only; data reset weekly | Reminder in each trial briefing | [DPO] | [DPO] |
| R14 | Nightly backups leave Zambia | Backup target in Zambia specified | IT to confirm | [DPO] | [DPO] |

## 8. Data subject rights

- **Access and deletion:** a customer can be found by the hash of their
  channel id (staff compute it from the platform id they are given) or by
  ticket reference. **[DPO: procedure and who runs it]**
- **Objection to marketing:** opt-out commands in chat; staff remove the
  Jira label. **[DPO: other routes?]**
- **Information:** privacy notice (L3); the bot discloses it is automated
  in its first message.

## 9. Open questions for the DPO

1. Lawful basis for each purpose (§2.4) and for the transfers to Meta (L2).
2. Is financial information (for example what a customer says about a
   fraud) "sensitive personal data" under the Act? If so, masking becomes a
   compliance control, not just hygiene.
3. May tickets go to Atlassian Cloud, and with which fields (§4)?
4. Retention for each row of §5, including tickets and nginx logs.
5. Is the marketing-consent design (§2.2, lead flow) acceptable?
6. Do the evaluation sets in git (masked customer phrasings) need their own
   retention or approval?
7. Does the ODPC registration need updating (L8)?
8. Should phone numbers be masked in free-text fields (R5)?

## 10. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| DPO | | | __/__/____ |
| Compliance | | | __/__/____ |
| Product owner | | | __/__/____ |
