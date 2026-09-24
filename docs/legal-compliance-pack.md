# Legal and compliance pack

> **Draft brief for Legal / the DPO and Compliance**, prepared by the project
> on 24/09/2026. It is not legal advice. Every statute, section and
> directive cited here comes from the project's own research
> (`multi-platform-research.md` §3) and must be **confirmed against the
> official text**. Facts about the bot are taken from the code at the time
> of writing.

## 1. Summary

The bank is building a customer assistant for the website, WhatsApp and
Messenger. It answers questions from approved wording, takes fraud reports,
complaints and callback requests, and hands customers to staff. It has no
account access and no generative AI. Legal and Compliance decisions are the
critical path: the website launch (M3, target 07/12/2026) needs L1, L3, L4,
L5 and L8; WhatsApp (M4, staff pilot from 04/01/2027) also needs **L2**,
which has a hard stop in W14 (by 01/01/2027).

**The decisions we need, by deadline:**

| # | Question | Owner | Due (from `execution-plan.md` §10) | Blocks |
|---|---|---|---|---|
| L8 | Does the ODPC registration cover the assistant and name its processors? | DPO | W04 (23/10/2026) | M3 |
| L1 | DPIA for all three channels and the local models | DPO | W06 (06/11/2026) | M3 |
| L3 | Privacy notice and first-contact wording | Legal + CO | W06 (06/11/2026) | M3, M4 |
| L5 | Retention periods | Legal | W06 (06/11/2026) | M3 |
| L7 | Approval of the local, non-generative models | Legal / DPO | W08 (20/11/2026) | Hybrid matcher in production |
| L4 | Bank of Zambia cyber / IT-risk engagement | Compliance | W10 (04/12/2026) | M3 |
| L6 | Utility template wording | Legal | W10 (04/12/2026) | WhatsApp templates |
| L2 | DPA s.70/71: Meta processing outside Zambia | Legal | W10 (04/12/2026), **hard stop W14** | **M4, M5** |
| — | Jira (Atlassian Cloud?) holding ticket data outside Zambia | Legal + DPO | W06, with L1 | Real Jira at M3 |
| — | Cyber Security Act 2025: is anything Critical Information Infrastructure? | Compliance | W10, with L4 | M3 |
| — | BoZ Complaints Directive: acknowledgement and resolution timelines | Compliance | W06 | M3 (complaint wording) |
| — | Marketing consent and lead generation (§3) | Legal + Marketing | W06 | Any marketing use of leads |

## 2. The questions one by one

### 2.1 L1 · Data protection impact assessment

- **Question.** Is a DPIA required, and does the draft in `docs/dpia-draft.md`
  cover the processing adequately?
- **Why it matters.** The assistant processes customers' messages, names,
  phone numbers and (on WhatsApp and Messenger) platform identifiers, across
  three channels and several processors.
- **What the bot does today.** See the pre-filled draft: data inventory
  per flow and channel, data flows, processors, retention and controls.
- **Decision needed.** DPO completes and signs the DPIA, including the
  lawful-basis column the project has left blank.
- **Deadline.** W06 (06/11/2026). Blocks M3.

### 2.2 L2 · Data Protection Act s.70/71: Meta outside Zambia

- **Question.** On what lawful basis can WhatsApp and Messenger messages be
  processed by Meta outside Zambia? Is an ODPC authorisation, an approved
  contract, or customer consent (or a combination) needed?
- **Why it matters.** Research notes that s.70 requires processing and
  storage in Zambia, and s.71 allows cross-border transfer only under set
  conditions (consent plus approved contracts, a ministerial prescription,
  or a specific ODPC authorisation). With the WhatsApp Cloud API, Meta
  decrypts messages in its own data centres and keeps them for up to 30
  days; its local-storage option lists no African country **[VERIFY current
  list]**. Other Zambian banks run WhatsApp bots, so a route exists; peers
  (for example through the Bankers Association of Zambia) may share theirs.
  *Confirm against the official text.*
- **What the bot does today.** The bank's own server (to be hosted in
  Zambia) holds all records. Meta sees the messages in transit because it
  runs the channel. The bank's side stores only hashed platform ids in logs
  (`app/identity.py`), seals the raw id needed to reply with a key held on
  the bank's server, masks card, NRC, account and PIN numbers before
  anything is stored (`app/guards.py`), and never downloads photos, files or
  voice notes (`app/channels/messaging.py`).
- **Decision needed.** The lawful basis; whether ODPC action is needed; the
  wording the customer sees on first contact (feeds L3).
- **Deadline.** W10 (04/12/2026); **hard stop W14 (01/01/2027)**. If it
  slips, WhatsApp and Messenger wait; the website does not.

### 2.3 L3 · Privacy notice and first-contact wording

- **Question.** What must the privacy notice on abbank.co.zm say about the
  assistant, and what must the bot say on first contact on each channel?
- **Why it matters.** Transparency duties under the DPA; Meta's Messenger
  App Review requires a privacy-policy URL (`messenger-app-review.md` §4 lists
  what it must cover); Messenger policy asks for bot disclosure.
- **What the bot does today.** The first message says it is "an automated
  helper, not a person" (`welcome` in `knowledge/system_messages.yaml`,
  `status: draft`). There is no link to a privacy notice yet.
- **Decision needed.** Approved privacy-notice text and URL; approved
  first-contact wording per channel (including any consent line L2
  requires).
- **Deadline.** W06 (06/11/2026). Blocks M3 and M4.

### 2.4 L4 · Bank of Zambia cyber and IT-risk engagement

- **Question.** What do the BoZ Cyber and Information Risk Management
  Guidelines (gazetted May 2023) require for this channel: hosting approval,
  third-party risk assessment of Meta, the data centre and Atlassian, and
  any notification to BoZ?
- **Why it matters.** It is a production customer channel. Research
  flags that an unsupported channel would be hard to defend under the
  Guidelines. *Confirm against the official text.*
- **What the bot does today.** Designed for one VM in Zambia
  (`hosting-requirements-it.md`); admin pages behind HTTP Basic auth and
  hidden (404) until credentials are set; per-IP and per-customer rate
  limits; kill switches that work without a restart; webhook signatures
  checked on every Meta request.
- **Decision needed.** Compliance's list of requirements and whether BoZ
  must be notified; IT-risk sign-off of the hosting.
- **Deadline.** W10 (04/12/2026). Blocks M3.

### 2.5 L5 · Retention periods

- **Question.** How long may the bank keep chat transcripts, tickets,
  sessions and the evaluation sets?
- **Why it matters.** The DPA's storage-limitation principle, balanced
  against complaint and fraud record-keeping duties.
- **What the bot does today** (`app/config.py`, placeholders pending Legal):
  - `TRANSCRIPT_RETENTION_DAYS = 90`: audit events and sessions are deleted
    after 90 days;
  - `TICKET_RETENTION_DAYS = 0`: tickets are **never** deleted automatically
    ("complaint/fraud tickets follow the complaints unit's policy");
  - the WhatsApp/Messenger inbox table has a purge function that is not yet
    scheduled (being fixed under R1);
  - copies in Jira and backups follow their own systems' rules.
- **Decision needed.** A number of days for each; what happens to tickets
  once closed; how long backups are kept (the plan says 14 days).
- **Deadline.** W06 (06/11/2026). Blocks M3.

### 2.6 L6 · Utility template wording

- **Question.** Is the wording of the three WhatsApp templates in
  `knowledge/templates.yaml` (`case_received`, `case_update`,
  `callback_scheduled`) acceptable?
- **Why it matters.** Outside the 24-hour window only an approved template
  can be sent. Scammers imitate exactly these messages; Meta re-categorises
  anything promotional as marketing.
- **What the bot does today.** Drafts are neutral, contain no links, always
  quote the case reference, and never ask for details. Staff send
  `case_update` from `/admin/cases`.
- **Decision needed.** Approved wording.
- **Deadline.** W10 (04/12/2026).

### 2.7 L7 · Local, non-generative models

- **Question.** May the bank use two small local models: a sentence-embedding
  model to understand free text (all-MiniLM-L6-v2, Apache-2.0) and the same
  model as a second check for fraud wording?
- **Why it matters.** Automated processing of customers' messages;
  model governance.
- **What the bot does today.** The model runs on the bank's own server; no
  message leaves it for this purpose. It only chooses among approved
  answers; it never writes text. The model file is checked against a pinned
  hash. It is **off** in production by default (`EMBEDDINGS_ENABLED`),
  pending shadow-mode results.
- **Decision needed.** Approval (or conditions).
- **Deadline.** W08 (20/11/2026).

### 2.8 L8 · ODPC registration

- **Question.** Does the bank's registration with the Office of the Data
  Protection Commissioner cover the assistant on all channels and name its
  processors (the Zambian host, Meta, and Atlassian if used)?
- **Why it matters.** Research notes registration was due by 30/04/2025 and
  failing to register is an offence. *Confirm against the official text.*
- **Decision needed.** Confirmation, or an update to the registration.
- **Deadline.** W04 (23/10/2026). Blocks M3.

### 2.9 Jira: ticket data outside Zambia

- **Question.** May fraud, complaint and callback tickets be copied into the
  contact centre's Jira if Jira is Atlassian Cloud (hosted outside Zambia)?
- **Why it matters.** Each ticket carries the customer's name and phone
  number or email (if given), the channel, a hashed id, and the full
  **masked** transcript (`app/jira_export.py`). That is a cross-border
  transfer under s.71 unless Jira is hosted in Zambia. The deployment guide's
  example address (`abbank.atlassian.net`) suggests Atlassian Cloud
  **[CONFIRM with the contact centre which Jira they use]**.
- **What the bot does today.** Jira runs in **mock mode**: no credentials
  are set, so tickets are written to a local file only. Real pushes start
  only when four environment variables are set.
- **Decision needed.** Allowed (on what basis), allowed with a reduced
  field set (for example reference and category only, with details kept on
  the Zambian server), or not allowed (Jira stays off, or an in-country Jira
  Data Center is used).
- **Deadline.** W06, with L1. Blocks turning on real Jira.

### 2.10 Cyber Security Act 2025: Critical Information Infrastructure

- **Question.** Is any system the assistant touches designated, or likely to
  be designated, Critical Information Infrastructure? If so, what follows
  (for example localisation or registration duties)?
- **Why it matters.** Research notes the Act lists banking and finance as a
  critical sector, and commentary describes localisation for CII **[VERIFY
  with counsel]**. *Confirm against the official text.*
- **What the bot does today.** It is separate from core banking: no account
  access, no connection to core systems. It is hosted in Zambia.
- **Decision needed.** Compliance's view, recorded with L4.
- **Deadline.** W10 (04/12/2026).

### 2.11 BoZ Customer Complaints Handling and Resolution Directives

- **Question.** What acknowledgement, resolution and escalation timelines
  must the bot quote when a complaint is logged?
- **Why it matters.** A complaint made through chat is a complaint. The
  bot's promise must match the Directive and the complaints unit's practice.
  *Confirm against the official text.*
- **What the bot does today.** The complaint flow takes the topic, details
  and a contact, shows a summary to confirm, creates a ticket with a
  reference (CMP-…) and says it goes to the complaints team "under the Bank
  of Zambia's complaints-handling requirements". The response-time
  commitment is a placeholder: `[CONFIRM: response-time commitment to quote
  here.]` (`complaint.finish` in `knowledge/system_messages.yaml`). Out of
  hours it adds when the team will pick it up. The bot never closes a
  complaint ticket itself.
- **Decision needed.** The exact timelines and wording to quote, and
  whether the bot must also tell customers how to escalate to BoZ.
- **Deadline.** W06 (06/11/2026), so Legal can approve the wording before
  M3.

## 3. Marketing consent and lead generation

**Context.** Marketing intends to use the assistant for lead generation.
The callback flow ("talk to a person") collects a name, phone number, topic
(for example "a loan") and a preferred time. As part of this week's build,
the callback flow is gaining **a marketing-consent question**: after the
callback details, the customer is asked whether the bank may contact them
about products, with a clear yes or no. Customers can withdraw at any time
with opt-out commands (for example "stop"). There is **no bulk export** of
leads: Marketing works from callback tickets carrying a Jira label for
consenting customers. (See `decisions-log.md`; each item is a proposal for
the PO to approve.)

**Questions for Legal:**

1. **ECT Act 2021.** Research notes unsolicited commercial communications
   need an opt-in and a working opt-out, and failing to provide an opt-out
   is an offence. Is the consent question's wording a valid opt-in? Does
   the opt-out need to work on every channel and by every route (chat
   command, call centre, email)? *Confirm against the official text.*
2. **DPA purpose limitation.** A callback number is given to get a call
   back about the customer's question. Using it for marketing is a new
   purpose: is separate, explicit consent (as proposed) sufficient, and
   what must the privacy notice say?
3. **Default.** The question is asked by default (the feature is on), but
   the answer is never assumed: a customer who doesn't answer, or says no,
   is not a lead. Please confirm this is acceptable, and whether "no" must
   be the first button.
4. **Record of consent.** The ticket records the answer, the time and the
   channel. Is that enough evidence, and how long must it be kept (L5)?
5. **WhatsApp marketing messages.** Meta requires opt-in for
   business-initiated messages and charges marketing templates separately.
   The project recommends **no marketing messages on WhatsApp or Messenger
   at launch**: Marketing calls consenting leads by phone. Please confirm.
6. **Campaign attribution.** Links and QR codes may carry a short campaign
   code (for example a branch name) so Marketing can see which campaign
   brought a conversation. It identifies a campaign, never a person. Please
   confirm no further notice is needed.

**Deadline.** W06 (06/11/2026). Until Legal rules, the PO should treat
leads as callback requests only.

## 4. What the project needs back

For each item: a short written answer (email or memo reference is enough),
any wording to use, and the name of the person deciding. The PO records
them in `go-no-go.md`.
