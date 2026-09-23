# Multi-platform chatbot: research and execution plan

**Website + WhatsApp + Facebook Messenger for AB Bank Zambia**

Researched 2026-09-23 · Status: research and recommendation. No application code changed yet.

> **How to read this.** §1 is the one-page answer. §2–§4 cover the facts that
> limit the design: what Meta changed in 2025–26, Zambian law, and the local
> market. §5–§7 give a playbook for each platform and map the architecture onto
> this repo. §8–§11 cover cost, roadmap, decisions and risks. Appendices A–B
> hold the platform limits and a content audit measured against this repo.
>
> **Source caveat.** Meta's developer docs (`developers.facebook.com`) couldn't be
> reached from the research environment. The platform facts here come from
> Meta-partner documentation (360dialog, Twilio, Infobip, Chatwoot, etc.) and
> industry coverage, all cited in §12. Anything marked **[VERIFY]** must be
> checked against Meta's own docs or rate card before it goes into a budget, a
> contract, or customer-facing text. The legal points are research for the legal
> team, not legal advice.

---

## 1. The one-page answer

**Recommendation: one brain, three mouths.** Keep the deterministic core as the
single source of truth: router, matcher, flows, guards, audit and the YAML
knowledge base. Add thin *channel adapters* around it. The core already speaks a
channel-neutral language, because every reply is `{text, buttons[]}` and nothing
in `app/router.py` knows about HTML. So this is an extension, not a rewrite. Don't
buy a second bot platform, and don't start with an LLM.

**The ten things that decide whether this succeeds:**

1. **WhatsApp first, Messenger second, and the website stays.** WhatsApp is
   Zambia's dominant messaging app, with an estimated ~6M users against 4.1M
   social-media identities in total. Local competitors are already there: Zanaco's
   "Coco" launched on WhatsApp in May 2026, and Stanbic's "Stan" runs on WhatsApp
   and Messenger.
2. **WhatsApp bot replies stop being free on 1 October 2026, eight days from
   now.** Free-form "service" replies will be billed per message at each market's
   utility rate, after 1,000 free messages per number per month. So the design
   should send fewer, fuller messages. Today's router sends up to 2 bubbles per
   turn, and a lost-card report produces 6 bot messages (Appendix B).
3. **The launch blocker is data localisation, not code.** Section 70 of the Data
   Protection Act 2021 requires personal data to be processed and stored in
   Zambia. Meta processes WhatsApp and Messenger messages outside Zambia, and the
   current Render hosting is outside Zambia too. Before real customers use it, you
   need a legal ruling and Zambian hosting for the backend and audit database.
4. **Production hosting must be always-on.** Render's free tier sleeps, which
   takes 30–50 s to wake. Meta expects a webhook `200` within seconds and retries
   for up to 7 days, so a sleeping server produces duplicate and days-late
   messages. That, plus §3, points to one always-on VM in a Lusaka data centre.
5. **Both Meta channels require a human escalation path.** WhatsApp's policy
   demands "prompt, clear and direct" escalation whenever you automate, and
   regulators have criticised chatbot "doom loops". The existing "Talk to a
   person" option and ticket flow meet the minimum. A real agent inbox is the
   target.
6. **Identity is changing.** WhatsApp usernames (June 2026) mean the phone number
   may not arrive at all. Key users on the business-scoped user ID (`user_id`, or
   BSUID) and treat phone numbers and Messenger IDs as PII.
7. **Content must be re-cut for small screens.** 37 of 81 button labels are longer
   than 20 characters, which is a hard limit on both WhatsApp buttons and
   Messenger quick replies. The main menu and 15 of 44 answers have 4–5 buttons,
   but WhatsApp allows at most 3 reply buttons, so those need a list message. Add
   a `short_label` field and per-channel limit tests to the regression suite.
8. **Anti-impersonation is a feature.** Scammers posing as banks on WhatsApp are
   one of the most common fraud patterns. Get the verified badge, publish one
   official number everywhere, and keep the bot's "we never ask for your PIN or
   OTP" line.
9. **The session store must become persistent**, keyed by (channel, user).
   Messaging conversations span hours or days, and an in-memory store with a
   30-minute timeout loses every in-progress flow on each restart or deploy.
10. **Start the paperwork now.** Meta Business verification, the WhatsApp display
    name, Messenger App Review, the legal DPIA and ODPC position, and procuring
    Zambian hosting all take longer on the calendar than the engineering does.

---

## 2. What changed in 2025–2026

The platform rules moved a lot while V1 was being built. Most "how to build a
WhatsApp bot" material online is now out of date.

| When | Change | Why it matters here |
|---|---|---|
| 9 May 2024 | Facebook's Customer Chat Plugin (the Messenger widget for websites) was shut down | The website can't simply embed Messenger. It has to run its own widget, which this repo already does. |
| 23 Oct 2025 | WhatsApp On-Premises API retired. The Meta-hosted **Cloud API** is the only official option. | There's no self-hosted WhatsApp server to keep data in Zambia, so Meta always processes the messages (§3). |
| Oct 2025 | WhatsApp messaging limits now apply per business portfolio, not per phone number | Verifying the business once lifts limits for every number. |
| Q1–Q2 2026 | The 2K and 10K tiers were removed. A verified business goes straight to 100K business-initiated messages a day. | Volume limits won't constrain us. The quality rating still matters. |
| 15 Jan 2026 | General-purpose AI assistants (ChatGPT-style) were banned from the WhatsApp Business Platform. A business's own customer-service bot, including an AI one, is still allowed. | Our bot is fine. A future V2 LLM is also fine as long as it serves AB Bank's own customer service. |
| 31 Mar 2026 | The business-scoped user ID (`user_id`) was added to every WhatsApp webhook | Use it as the primary key for WhatsApp users. |
| Jun 2026 | WhatsApp usernames launched. A user's phone number may be hidden. | The callback flow can't assume we already know the customer's number. |
| Dec 2025 → Apr 2026 | Messenger desktop apps discontinued, then messenger.com shut (users go to facebook.com/messages) | Messenger's audience is now almost entirely on mobile. |
| 27 Apr 2026 | Messenger tags `ACCOUNT_UPDATE`, `CONFIRMED_EVENT_UPDATE` and `POST_PURCHASE_UPDATE` retired and replaced by utility templates. `HUMAN_AGENT` (7 days, humans only) remains. | A case follow-up sent more than 24 h after the customer's last message needs a template. |
| 2025–26 | Messenger's "handover protocol" is being replaced by **conversation routing** **[VERIFY current setup screens]** | This is the mechanism for handing a conversation from the bot to the Page Inbox. |
| 3 Jun 2026 | **Meta Business Agent** launched: Meta's own hosted AI agent. Token billing started 1 Aug 2026. | It's a "buy" option, but not recommended for V1: it's an LLM, it's behind the same legal gate as V2, and one analysis puts it at ~4–5 US cents per message **[VERIFY]**. |
| **1 Oct 2026** | **WhatsApp service messages** (free-form replies inside the 24-h window, whether from a human or a bot) are **charged per message** at the market's utility rate, after **1,000 free per number per month**. Utility templates sent inside the window are also charged. A WhatsApp account with no payment method on file stops delivering service messages. | This changes both the cost model and the UX design (§8). |
| 2025 | **Coexistence** lets one number run on the WhatsApp Business app and the Cloud API at the same time | This is an option for the number already in use, 0769651262 (§5.1). |

---

## 3. Zambian legal and regulatory constraints (for legal and compliance)

Take this section to the legal team and the DPO first. It decides whether and
where the bot can run. The engineering in §7 can proceed in parallel.

### 3.1 Data Protection Act No. 3 of 2021

- **s.70, localisation.** Data controllers must process and store personal data
  on a server or data centre located in Zambia. *Sensitive* personal data may only
  be stored in Zambia. The Minister may prescribe categories of data that are
  allowed abroad.
- **s.71, cross-border transfer.** A transfer is allowed only under one of these
  conditions:
  - the data subject consents *and* the transfer uses standard contracts or
    intragroup schemes approved by the Data Protection Commissioner;
  - the Minister has prescribed that the transfer is permissible;
  - the Commissioner has authorised the specific transfer.
- **Registration.** Data controllers and processors had to register with the
  Office of the Data Protection Commissioner (ODPC) by 30 April 2025. Failing to
  register is an offence carrying a fine of up to ZMW 200,000 and/or up to five
  years' imprisonment.

**What this means for the build:**

- **(a) The backend, audit DB and tickets must be hosted in Zambia.** The Render
  deployment in `docs/deployment-and-jira-setup.md` is fine for a demo with fake
  data. It is not a production answer, and that is already true for the website
  bot on its own.
- **(b) The Meta channels involve cross-border processing by design.** With the
  Cloud API, Meta decrypts messages in its own data centres and keeps them for up
  to 30 days. Meta's "local storage" option covers a list of APAC and European
  regions that includes no African country **[VERIFY current list]**. Legal needs
  to decide the lawful basis, for example:
  - the customer starts the contact;
  - the customer sees a privacy notice and gives consent on first contact;
  - Meta and the hosting provider are recorded as processors;
  - the ODPC authorises the transfer or approves the contract.

  Zanaco and Stanbic already run WhatsApp bots in Zambia, so a workable route
  evidently exists. It would be worth asking peers how they handled it, for
  example through the Bankers Association of Zambia.
- **(c) Confirm what counts as "sensitive" personal data under the Act.** If
  financial identifiers are included, the masking in `app/guards.py` stops being
  just good hygiene and becomes a compliance control. Its tests should then be
  treated that way.
- **(d) Confirm that AB Bank's ODPC registration covers chatbot processing** on
  every channel and names the processors: the Zambian host and Meta.

### 3.2 Cyber Security Act 2025 and Cyber Crimes Act 2025

These replaced the 2021 act. The Cyber Security Act lists banking and finance as a
critical sector, and commentary describes a data-localisation requirement for
Critical Information Infrastructure (CII). Ask compliance whether any system the
chatbot touches is, or could be, designated CII **[VERIFY with counsel]**.

### 3.3 Bank of Zambia

- **Cyber and Information Risk Management Guidelines (gazetted May 2023).** These
  cover third-party, cloud and outsourcing risk. The repo notes that IT isn't
  supporting this project, but a production customer channel on WhatsApp will
  very likely need IT-risk/CISO sign-off under these guidelines. Raise this early
  rather than at go-live.
- **Customer Complaints Handling and Resolution Directives.** A complaint made
  through chat is a complaint. The bot already issues a reference number, and it
  should also match the Directive's acknowledgement and escalation wording and
  timelines. Pull the exact timelines from the Directive and encode them in the
  complaint flow's promises **[VERIFY Directive text]**.

### 3.4 Electronic Communications and Transactions Act 2021

Unsolicited commercial communications need an opt-in and a working opt-out, and
failing to provide an opt-out is an offence. **Recommendation:** in the
multi-channel launch, send no marketing at all. Send only replies to
customer-initiated messages and utility case updates. If marketing is added
later, it needs explicit opt-in capture and "STOP" handling first.

### 3.5 Platform policies (these are contractual terms)

- **WhatsApp Business Messaging Policy.**
  - If you automate, you must offer a prompt, clear, direct escalation path.
  - Business-initiated messages need opt-in.
  - Template categories are enforced: since April 2025, Meta automatically
    re-categorises a "utility" template to "marketing" if it contains promotional
    language.
- **Messenger policy.**
  - Where the law requires it, disclose that the user is talking to a bot. Meta
    recommends doing so everywhere.
  - `HUMAN_AGENT` is for human replies only.
  - Free-form messages are allowed only within 24 h of the user's last message.
- The current `WELCOME_TEXT` ("an automated helper, not a person") already
  discloses the bot. Keep it on the first contact in every channel.

---

## 4. Market context: who we're building for

- **Reach (DataReportal Digital 2026 Zambia; Yazi):**
  - 7.29M internet users (33% of the population)
  - 4.10M social-media user identities (18.6%)
  - 23.5M mobile connections (106%)
  - WhatsApp at roughly 6M users (an estimate)

  More people message than browse, so WhatsApp is the primary channel.
- **Data costs shape the UX.** All three operators sell social-only data bundles,
  and MTN's Pulse plan includes free WhatsApp. Many customers can use WhatsApp but
  can't open a web link. **Answers on WhatsApp must be complete inside the chat.**
  A link can be an optional extra, never the answer itself. Five current answers
  lean on links: `bank_statement_request`, `etumba_fees`, `fees_charges`,
  `personal_loan` and `contact_details`.
- **Language.**
  - Bemba ~34%, Tonga ~13%, Nyanja ~11% (plus Chewa ~7%), Lozi ~5%.
  - English is a first language for only ~2% of people, but it's the most common
    second language.

  So keep the English short and plain. The matcher already handles "muli bwanji",
  "zikomo", "natotela" and "twalumba". Bemba and Nyanja menus are a sensible later
  phase.
- **Voice notes.** Vendors report that voice notes dominate customer messaging in
  several African markets. The bot must respond gracefully to a voice note
  ("I can only read typed messages for now", plus buttons). Transcription is V2
  work with its own data-protection questions.
- **Competitors in Zambia:**
  - **Zanaco "Coco"** (WhatsApp, launched May 2026) is transactional: transfers,
    bills and cash-out. It requires the customer to be registered for mobile
    banking, and Zanaco stresses that the PIN is never stored in chat history.
  - **Stanbic "Stan"** runs on WhatsApp, Messenger and Telegram. It answers FAQs
    on mobile banking, insurance, loans and POS, and there is a separate WhatsApp
    assistant for Enterprise clients.
  - Regionally, **Absa's "Abby"** runs in 8 countries, and **UBA's "Leo"** has
    been on WhatsApp and Messenger since 2018.
- **Honest positioning.** V1 is informational, lead-generating and routes fraud
  and complaints. Staying non-transactional is a defensible, lower-risk choice.
  But customers will compare the bot with Zanaco's transactional one, so expect
  "can I check my balance?" as one of the top unmatched questions. Give it a
  clear, pre-approved answer that points to eTumba (`*888#`) and MyABZ.
- **The 24/7 gap gets more visible.** `config.CONTACTS["emergency_phone"]` is
  still `[CONFIRM …]`, and the FAQ notes there is no after-hours card-block line.
  An always-on WhatsApp channel will receive fraud reports at 22:00 on a Sunday.
  Ops needs to decide what the fraud flow promises out of hours *before* launch.

---

## 5. Platform playbooks

### 5.1 WhatsApp (Cloud API)

**Setup chain.** This is mostly calendar time, so start it in Phase 0.

1. Set up a **Meta Business portfolio owned by the bank**, with at least two bank
   admins. It must not belong to an individual or an agency. Then complete
   **Business verification** (company documents).
2. Create a Meta app with the WhatsApp product, then a WhatsApp Business Account
   (WABA). Register the phone number, pass **display-name** review, and set the
   **two-step verification PIN**.
3. Provide a public HTTPS **webhook**: an always-on URL with a verify token.
   Subscribe to `messages`.
4. Add a **payment method** to the WABA. From 1 Oct 2026, service messages aren't
   delivered without one.
5. Apply for an **Official Business Account** (the blue badge, which is free). It
   requires an API number, a verified business, 2FA, and a display name that
   matches the company. Some sources add a minimum messaging tier **[VERIFY]**.
   Meta Verified for Business is the paid alternative.
6. Submit **utility templates** for case follow-ups (see "24-hour window" below).

**The number decision.** AB Bank already publishes **0769651262** as its
WhatsApp number, presumably staffed today by people using the WhatsApp Business
app.

| Option | Pros | Cons |
|---|---|---|
| **A. Migrate 0769651262 fully to the Cloud API** | Keeps the number already printed everywhere. Eligible for the blue badge. One bot handles everything. | Business-app chat history is lost (back it up first). Staff need a new tool to reply (§7.6). It's a hard cutover. |
| **B. Coexistence on 0769651262** | Staff keep using the Business app with their history. The bot runs on the API alongside them. Low risk. | **No blue badge** (only paid Meta Verified). The app must be opened at least every 13 days. Two writers means the bot must pause when a human replies (§7.6). Messages sent from the app are free, but API messages are billed. |
| **C. A new number just for the bot** | Clean start. | Customers get confused, and scammers get a second "official" number to imitate. |

**Recommendation:** build and test against Meta's free test number. For the
pilot, use **B** if the social team currently answers on 0769651262. Move to
**A** plus the blue badge once the agent inbox (§7.6) exists. Confirm with Meta,
or with a partner, that moving from coexistence to API-only later is supported
**[VERIFY]**.

**The 24-hour customer-service window.** Free-form replies are allowed only
within 24 h of the customer's *last* message. After that, only a pre-approved
**template** can be sent. For us, that means a fraud or complaint follow-up from
staff on day 2 needs a utility template. Prepare three, worded neutrally so Meta
doesn't re-categorise them as marketing:

- `case_received`
- `case_update` ("Hello, this is AB Bank about your case {{1}}. Please reply to
  this message to continue.")
- `callback_scheduled`

Scammers imitate exactly this kind of message, so templates must never contain
links that ask for details. They should always quote the reference the customer
already has.

**Building blocks** (limits in Appendix A):

- **Reply buttons**: at most 3, each title at most 20 characters. Use them for
  answers with 1–3 next steps.
- **List message**: one menu button that opens up to 10 rows. Row titles are
  limited to 24 characters, and each row has an optional description. Use it for
  the main menu (5 items), the city picker (7 items), "Did you mean…?" and any
  answer with 4–5 buttons.
- **Location request**: a message with a native "Send location" button. The
  webhook returns latitude and longitude, which is a perfect fit for "nearest
  branch". `knowledge/branches.json` needs coordinates added.
- **WhatsApp Flows**: native multi-screen forms. *Static* flows have no endpoint.
  *Dynamic* flows call an encrypted endpoint. They're a good later upgrade for
  the complaint and callback forms, but the data still passes through Meta, so
  keep sensitive fields out.
- **Mark as read + typing indicator**: shows blue ticks and "typing…" until we
  reply (or ~25 s). It's cheap and makes the bot feel responsive.
- **Inbound media**: images, documents, audio, video, stickers, locations and
  contacts. See the media policy in §7.5.
- **Old buttons stay tappable.** A customer can tap yesterday's "Lusaka" button
  long after the locator flow has ended. Make button IDs self-describing, e.g.
  `loc_city:Lusaka` rather than `Lusaka`, so a stale tap still does the right
  thing instead of hitting the `unknown_payload` fallback.

**Webhook engineering.** This is where WhatsApp bots usually break.

- **Verify `X-Hub-Signature-256`.** It's an HMAC-SHA256 of the *raw* body using
  the app secret. Reject anything that fails.
- **Acknowledge fast.** Return `200` within seconds (sources cite 3–5 s) and
  process the message afterwards.
- **Delivery is at-least-once, so duplicates are normal.** Deduplicate on the
  message ID (`wamid`).
- **Retries back off for up to 7 days, and there's no replay API.** After an
  outage, messages arrive hours or days late. Check each message's timestamp: if
  it's old, lead with an apology and the menu rather than resuming a flow that has
  gone stale.
- **Status webhooks** (sent / delivered / read / failed) feed delivery metrics and
  retry decisions.
- **Order isn't guaranteed, and users send bursts** ("hi", "I lost my card",
  "pls help"). Process each user's messages one at a time. Optionally, merge a
  1–2 s burst into one turn so the bot doesn't send three replies (and three
  billable messages).

**Throughput and quality.** The default is ~80 messages per second, which is not
a constraint at our scale. The quality rating (blocks and reports) mainly affects
business-initiated sends. Staying reply-only keeps the risk low.

### 5.2 Facebook Messenger

**Setup:**

1. Put the existing Facebook Page in the same business portfolio, and add the
   Messenger product to the **same Meta app**. Business verification is shared
   with WhatsApp.
2. Configure the webhook for messages, postbacks, echoes, and handover/standby
   events. Handling comments (private replies, below) needs extra Page
   permissions **[VERIFY exact permission names]**.
3. **App Review.** `pages_messaging` needs **Advanced Access** before the bot can
   talk to the public rather than just Page admins. That requires:
   - business verification
   - a privacy-policy URL
   - a **screencast** of a real conversation
   - test credentials for Meta's reviewers

   Mismatches between the screencast and the stated use case are the most common
   rejection reason. Budget for at least one resubmission.
4. **Page profile.** Set up the "Get Started" button, greeting text, a
   **persistent menu** that mirrors `MENU_BUTTONS` and always includes "Talk to a
   person", and **ice breakers** (3–4 starter questions).

**Messaging windows:**

- Free-form messages are allowed up to 24 h after the user's last message.
- A human agent (never the bot) can reply for up to **7 days** using the
  `HUMAN_AGENT` tag.
- After that, only utility templates can be sent. Marketing messages need opt-in.

**Handing over to humans.** Use conversation routing (formerly the handover
protocol).

1. The bot's app is the default receiver, and the **Page Inbox** in Meta Business
   Suite is where staff reply.
2. On "Talk to a person", the bot passes thread control to the Page Inbox. Older
   integrations do this with `pass_thread_control` to the Page Inbox app ID
   `263902037430900`.
3. The bot stops replying.
4. When the agent marks the conversation "Done", control returns to the bot.

The social team probably already works in Business Suite, so this handoff costs
nothing and needs no new tool **[VERIFY against current conversation-routing
docs]**.

**UI limits:**

- Quick replies: at most 13, each title at most 20 characters. They disappear
  once used, so the persistent menu is the always-available escape hatch.
- Button template: at most 3 buttons and 640 characters of text. Plain text can
  run to 2,000 characters.
- One current answer, `business_account_requirements` at 755 characters, exceeds
  640. Send it as plain text with quick replies rather than as a button template.

**Private replies to comments.** This is the biggest win for the social team.

- The Page can send **one** private message per public comment or visitor post,
  within **7 days** of it, text only.
- If the person replies, a normal 24-h window opens.
- So when someone posts "you stole my money!!" under an ad, the bot can reply
  privately with the fraud entry point, and comms can post an approved public line
  such as "We've sent you a private message".

**Recommendation:** send automatic private replies only for comments that match
the urgent or complaint patterns in `guards.urgent_scan`. Keep public replies
human-approved.

**Webhooks.** The same rules apply: verify the signature, return `200` within
~5 s, and deduplicate. Messenger's retry window is shorter than WhatsApp's, and a
subscription that keeps failing (from ~15 minutes) raises developer alerts and
can be disabled **[VERIFY]**.

**Cost.** Meta doesn't charge per message for standard Messenger customer
service.

### 5.3 Website (the existing widget)

The widget is already strong: WCAG 2.1 AA, a kill switch, cross-domain embedding,
and the WordPress plugin. Improvements for the multi-channel world:

- **Cross-channel exits.** Add "Continue on WhatsApp" (`wa.me/260769651262` with
  pre-filled text) and "Message us on Messenger" (`m.me/<page>`) as optional
  buttons. Never put session state or PII in these URLs.
- **Mobile.** Show a full-screen panel on narrow viewports and keep the payload
  light: no web fonts, no images.
- **The web is the cheapest channel.** It has no 24-h window and no per-message
  fee, so it's the right home for longer content and satisfaction surveys.
- **Live chat later.** If Chatwoot is adopted (§7.6), a handoff from the web can
  become live chat inside the same widget instead of a callback ticket.

### 5.4 Instagram (optional, cheap later)

Instagram direct messages use the same Meta app and Messenger Platform APIs, with
their own permission and App Review. The Social Media Response Template shows
customers already message the bank on Instagram, so it's a natural Phase 4
extra. LinkedIn is out of scope.

---

## 6. Best practices: what makes the good ones good

These are drawn from the regulator criticism of bank chatbots (CFPB's review of
chatbots in consumer finance), Nielsen Norman Group's chatbot guidelines, Meta
policy, and the regional bank examples above. Each is checked against this repo.

| # | Principle | Why | In this repo today | Multi-channel action |
|---|---|---|---|---|
| 1 | **Say what you are and what you can do** | Hiding the bot's scope leads to dead ends and bad expectations | ✅ `WELCOME_TEXT` discloses the bot and states its scope | Send it on first contact per channel, and again after a long idle gap |
| 2 | **One tap to a human, always** | Required by WhatsApp policy; "doom loops" are the main complaint about bank bots | ✅ `human_handoff` works mid-flow | WhatsApp buttons scroll away, so make typed "agent", "person" or "0" work everywhere. On Messenger, put it in the persistent menu. |
| 3 | **No dead ends, and a two-strike rule** | Recovering from errors is where most bots fail | ✅ Enforced in `router.handle()` | The renderer must never drop the human option when it trims buttons to fit a platform limit |
| 4 | **Buttons plus free text** | Most users tap; some type | ✅ | Use WhatsApp lists and buttons. Let a typed "1"/"2" pick from the last numbered options. |
| 5 | **Context travels with the handoff** | Don't make the customer repeat themselves | ✅ The transcript rides on tickets | Add the channel and reply address to tickets so the agent answers *on the same channel* |
| 6 | **Write for messaging** | Small screens, low data | Partly | At most ~3 short paragraphs, one question per message, key fact first. Merge bubbles (§8). |
| 7 | **Global commands** | Users get lost in flows | Partly (`menu` payload) | Recognise typed "menu", "agent" and "stop" in any state |
| 8 | **Security as a feature** | Impersonation scams | ✅ PII masking and warning | Verified badge. Never ask for documents or photos in chat. Remind customers about scams inside the fraud flow. |
| 9 | **Honest service levels** | Customer trust; the complaints Directive | ✅ "within one working day" | Out-of-hours wording, plus the 24/7 fraud route decision (§4) |
| 10 | **Low-data, self-contained answers** | Social-only bundles | Partly | Links become optional extras, never the whole answer |
| 11 | **One content source, rendered per channel** | Keeps channels consistent and keeps the legal audit trail in one place | ✅ YAML plus git history | Add `short_label` and per-channel overrides, with tests. Git stays the compliance trail. |
| 12 | **Measure weekly and fix the top misses** | Continuous improvement | ✅ `admin.report` | Break results down per channel. Track delivery failures and cost per conversation. |
| 13 | **Feel responsive** | Perceived speed | n/a | Send mark-as-read and a typing indicator as soon as a message arrives |

**The metrics that matter** (per channel and per week):

- **Self-serve rate**: conversations resolved without a ticket.
- **Handoff rate**, and handoffs by intent.
- **Fallback rate and two-strike rate.** The top unmatched phrases feed the
  content backlog.
- **Time to first human response** and ticket SLA hit rate.
- **Delivery failure rate** from status webhooks.
- **WhatsApp cost per conversation.**
- Optional **CSAT**. On WhatsApp, every survey message costs money, so sample it
  or keep it web-only.

---

## 7. Architecture: executing this on the current codebase

### 7.1 Target shape

```
             ┌──────────── Meta Cloud (processes messages outside Zambia) ─────────┐
WhatsApp ────┤ WhatsApp Cloud API ──webhook──┐              ▲ Graph send API       │
Messenger ───┤ Messenger Platform ──webhook──┤              │                      │
             └───────────────────────────────┼──────────────┼──────────────────────┘
Website ── widget.js ── POST /chat ──┐       │              │
                                     ▼       ▼              │
       ┌──────────────────── AB Bank backend (always-on VM, Lusaka) ──────────────┐
       │ channels/web.py    channels/whatsapp.py    channels/messenger.py         │
       │   verify signature · durable inbox write · ack 200 · dedupe · normalise  │
       │                          ▼                                               │
       │ InboundMessage(channel, user_key, text | payload | location | media)     │
       │                          ▼                                               │
       │ router.handle()   ← UNCHANGED pipeline: guards → flows → matcher         │
       │                          ▼ replies [{text, buttons}]                     │
       │ render.py (per-channel limits & degradation) → outbox (retry/backoff) ───┘
       │ session store (SQLite) · audit (SQLite+JSONL) · tickets → Jira / inbox   │
       └──────────────────────────────────────────────────────────────────────────┘
```

The invariants in `CLAUDE.md` carry over unchanged:

- The adapters call `guards.mask()` through `router.handle()`, so nothing
  downstream sees unmasked text.
- The button guarantee stays in the router, and the renderer is only allowed to
  *re-shape* buttons, never remove them all.
- Fraud and complaint flows still never close their own tickets.

### 7.2 Change list, mapped to files

| File | Change |
|---|---|
| `app/channels/` (new) | `base.py`: the `InboundMessage` dataclass and a `Channel` interface (`parse`, `send`, `mark_read`). `web.py`: today's `/chat` logic moved out of `main.py`. `whatsapp.py` and `messenger.py`: webhook GET verify, POST signature check, parse, send. |
| `app/render.py` (new) | Turns `[{text, buttons}]` into each channel's native payload using the rules in §7.3. It is pure functions, so it's easy to test against every intent. |
| `app/session.py` | Move to a **persistent** store (SQLite; the process stays single). Key it by `channel:user_key`. Separate the *greeting/idle* timeout from *flow* expiry. Store `last_inbound_at` (for the 24-h window), `bot_paused_until` (for human handoff) and `last_options` (for numeric replies). |
| `app/router.py` | Mostly unchanged. Add a `channel` context for per-channel content variants. Add global typed commands ("menu", "agent", "stop"). Add an optional "merge replies" mode that joins the PII warning or flow intro with the next prompt into one message. |
| `app/guards.py` | Add a media policy reply. Keep phone numbers from metadata out of the free-text path. |
| `app/audit.py` | Add a `channel` column and store an **HMAC of the user key**, not the raw phone number or ID. Record message status events. Give tickets `channel` and a (minimised) `reply_to`. |
| `app/main.py` | Mount the webhook routes. Keep the **per-IP rate limiter on `/chat` only**, because every webhook comes from Meta's IPs and a per-IP limit would throttle all WhatsApp users together. Add a **per-user** limiter for webhooks. Start the background worker in `lifespan`. |
| `app/config.py` and `flags.json` | Add `WHATSAPP_ENABLED` and `MESSENGER_ENABLED`. Add secrets: WhatsApp token, phone-number ID, app secret, verify token, Page token. |
| `knowledge/intents/*.yaml` | Add a `short_label` of 20 characters or fewer, needed by 37 of 81 labels. Add an optional `answer_by_channel`. For example, `contact_details` on WhatsApp shouldn't say "WhatsApp us on 0769651262". |
| `knowledge/branches.json` | Add `lat`/`lng` for location-based "nearest branch". |
| `tests/` | Add per-channel contract tests with recorded webhook payloads (good and bad signature, duplicate, stale, media, list reply, button reply). Add a renderer-limits test run over **every** intent, so a content edit that breaks WhatsApp limits fails CI the same way a dead end does today. |

### 7.3 Rendering rules (graceful degradation)

| Replies with… | Website | WhatsApp | Messenger |
|---|---|---|---|
| 1–3 buttons | As today | Reply buttons (`short_label`, ≤20 chars) | Quick replies (≤20 chars) |
| 4–10 buttons | As today | **List message**: button text "Choose an option", row title ≤24 (`short_label`), full label in the row description | Quick replies (up to 13) |
| >10 buttons | As today | The first 9 rows plus "More…" (none today; the largest is 8) | The first 12 plus "More…" |
| Body >1024 chars | As today | Send text first, then an interactive message with a short body. **Avoid this**, because it costs an extra message. Every current answer is 755 chars or fewer. | Body >640 → plain text plus quick replies, not a button template |
| Links | Clickable | Optional extra, never the answer (social bundles) | Clickable |
| Old buttons tapped later | Widget disables them | Stay tappable, so use self-describing IDs | Postback buttons persist; quick replies don't |

### 7.4 Webhook pipeline (sketch)

```python
@app.get("/webhooks/whatsapp")          # one-time subscription handshake
def wa_verify(hub_mode: str = Query(alias="hub.mode"),
              hub_token: str = Query(alias="hub.verify_token"),
              hub_challenge: str = Query(alias="hub.challenge")):
    if hub_mode == "subscribe" and hmac.compare_digest(hub_token, config.WA_VERIFY_TOKEN):
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403)

@app.post("/webhooks/whatsapp")
async def wa_webhook(request: Request):
    raw = await request.body()
    if not signature_ok(raw, request.headers.get("x-hub-signature-256"), config.WA_APP_SECRET):
        raise HTTPException(401)
    inbox.store(raw)        # durable write FIRST (SQLite), so an ack never loses a message
    worker.notify()         # single background worker, one user at a time
    return Response(status_code=200)
```

For each message, the worker does the following:

1. Skip it if the `wamid` has already been seen.
2. Look up the session.
3. Check whether the message is stale: over *N* minutes old means an apology and
   the menu, not a silent resume.
4. If the bot is paused because a human took over, log the message only.
5. Mark the message as read and show the typing indicator.
6. Call `router.handle()`.
7. Run `render.whatsapp()`.
8. Send, retrying 429 and 5xx responses with backoff.
9. Write to the audit log.

An in-process worker fits the current deliberate "exactly one process" design.
Moving to Redis with `arq` or `rq` is the scale-out step, the same trigger as
moving sessions.

**Library choice.** The Graph API surface we need is small: send text or
interactive messages, mark as read, and download media. A thin `httpx` client is
enough, and `httpx` is already in `requirements.txt`. [`pywa`](https://github.com/yehuda-lev/pywa)
(4.4.0, released 11 Aug 2026, supports FastAPI) is worth adopting if WhatsApp
Flows are added, since it handles Flow encryption.

### 7.5 Identity, PII and sessions

- **User keys:**
  - WhatsApp: the BSUID `user_id`, falling back to the phone-based `wa_id`.
  - Messenger: the page-scoped ID (PSID).
  - Web: today's random session ID.
- **The audit log stores `HMAC(secret, user_key)`, never the raw number or
  PSID.** Store a phone number only where the customer supplied it for a callback,
  as the lead flow already does.
- **Don't link identities across channels in V1.** Never treat "this message came
  from the WhatsApp number on the account" as authentication, because SIM swaps
  exist. V1 has no account access, so keep it that way.
- **Media policy.** Don't download or store inbound images or documents by
  default. A customer photographing their card or NRC is predictable, and
  `guards.mask()` can't redact an image. Reply once with a message like "For your
  safety I can't accept photos or files here. Please describe the problem in
  words, or talk to a person." Voice notes get the same treatment with different
  wording, until V2.
- **Lead flow on WhatsApp.** If the phone number is visible, offer a
  "Call me on this number" button with explicit consent. Otherwise, ask for the
  number as today.
- **Retention.** The persistent session store is purged on the same
  `TRANSCRIPT_RETENTION_DAYS` schedule as the audit log.

### 7.6 Human handoff: options

| Option | How it works | Cost | Verdict |
|---|---|---|---|
| **A. Tickets and callbacks** (what exists now) | "Talk to a person" → lead flow → Jira ticket → a call within one working day | Free | Fine for the pilot. On WhatsApp, the agent's follow-up after 24 h needs a template. |
| **B. Native inboxes** | Messenger: hand over to the Page Inbox (§5.2). WhatsApp: coexistence, where staff reply from the Business app and the bot **pauses** when it sees an `smb_message_echoes` event (a human replied). | Free | A good bridge. On WhatsApp: no blue badge, and a human and the bot could both be replying at once. |
| **C. A unified agent desk: [Chatwoot](https://github.com/chatwoot/chatwoot), self-hosted in Zambia** | Our bot keeps its connections to Meta and its native button rendering. On handoff, it mirrors the conversation into a Chatwoot **API-channel** inbox. Agents reply in Chatwoot, and those replies come back through our sender. The bot stays paused until the agent resolves the conversation. | Free open-source software plus hosting | **The recommended target.** One inbox for all three channels, the transcript attached, and data kept in Zambia. |
| **D. A commercial platform or BSP inbox** (Infobip, respond.io, etc.) | The vendor owns the channels and the inbox | Per-seat and/or per-message markup | Fastest to set up, but SaaS hosted abroad hits the s.70 problem, and it duplicates our bot. |

Why not let Chatwoot own the Meta channels and run our code as its "agent bot"?
Chatwoot's rich controls (cards, quick replies) render in its *website widget*,
while its handling of WhatsApp interactive messages has had silent-failure bugs
(buttons over the length limit are accepted but never delivered). Keeping the
channels ourselves preserves the button-first UX and the no-dead-end guarantee.

**Recommendation:** pilot with **A** everywhere, plus **B** for Messenger. Move
to **C** in Phase 4.

### 7.7 Kill switches, per channel

- `WIDGET_ENABLED` keeps its current meaning: the widget hides itself.
- `WHATSAPP_ENABLED` and `MESSENGER_ENABLED`: a Meta channel **can't be hidden**,
  so turning one off must mean "reply once with a static, pre-approved message
  (Contact Centre 888 and hours) and route to a human". It can never mean
  silence. On Messenger that also means passing thread control to the Page Inbox.
- `FREE_TEXT_ENABLED` applies to every channel: menu-only mode.
- `JIRA_ENABLED` is unchanged.

### 7.8 Hosting and operations

- **One always-on VM in a Zambian data centre.** Candidates include:
  - Paratus Lusaka: Tier III by design, ISO 27001, PCI DSS
  - Infratel: Tier 3
  - MTN Lusaka

  Get quotes. It needs a valid public TLS certificate, because Meta requires
  HTTPS.
- **Keep Render for demo and staging only**, with synthetic data.
- **Tokens.** Use a Business Manager **System User** access token for the Graph
  API, not a personal user token that expires or leaves with an employee. Store
  it in environment variables, never in `flags.json` or git.
- **Monitoring:**
  - webhook 4xx/5xx rates
  - send failures (status webhooks)
  - worker queue depth
  - the WhatsApp quality rating and template status
  - Meta's own webhook-failure alert emails, which should go to a shared inbox
- **Back up the SQLite files** (sessions, audit, tickets) daily. They're now
  production records.

### 7.9 Build versus buy for WhatsApp connectivity

| Route | Cost on top of Meta's fees | Fit |
|---|---|---|
| **Direct Meta Cloud API** | None | **Recommended.** We already have the backend, and our API needs are small. |
| 360dialog | Flat monthly fee per number; Meta's fees passed through at cost | A reasonable fallback if Meta onboarding stalls |
| Twilio | ~US$0.005 per message, in and out **[VERIFY]** | Adds cost and hides new Meta features behind another API |
| Infobip / Clickatell | Enterprise contracts | Strong African presence (Clickatell powers UBA's and Absa's chat banking). Worth it only if the bank wants a vendor SLA and account manager. |
| Meta Business Agent / other AI SaaS | Token or usage billing | Not for V1: it's an LLM, it's behind the legal gate, and it adds data-residency questions |

---

## 8. Cost model

- **Messenger:** Meta charges nothing per message for standard customer service.
- **Website:** hosting only.
- **WhatsApp, from 1 Oct 2026:**
  - Customer-to-bank messages are free.
  - **Service replies:** the first **1,000 per number per month are free**. After
    that, each costs the **utility rate for Zambia**. Zambia is on Meta's "Rest of
    Africa" rate card, and Meta said it would publish the per-market service rates
    around 1 Sep 2026 **[VERIFY exact figure]**.
  - **Utility templates** (case updates) are charged in or out of the window.
  - **Marketing** is about US$0.0225 per message in Rest of Africa **[VERIFY]**,
    and V1 plans none.
  - **Free entry point:** a chat that starts from a Click-to-WhatsApp ad or the
    **Facebook Page's WhatsApp call-to-action button** opens a 72-h window where
    service messages are free.

**Worked example.** This uses the bubble counts measured in Appendix B (3 bot
messages for an FAQ, 6 for a fraud report or callback, about 4.5 on average) and
an **illustrative** US$0.004 per message. Replace that with the published Rest of
Africa utility rate.

| Conversations/month | Bot messages | Billable after 1,000 free | ≈ Monthly cost |
|---|---|---|---|
| 1,000 | 4,500 | 3,500 | ≈ US$14 |
| 10,000 | 45,000 | 44,000 | ≈ US$176 |

That's small next to the cost of the contact centre, but it grows linearly with
how chatty the bot is.

**Cost levers** (all within our control):

1. Merge bubbles:
   - the PII warning plus the answer become one message;
   - the flow intro plus the first question become one message.

   That alone removes one message from every fraud report and every PII warning.
2. Don't add "Did that help?" follow-ups on WhatsApp.
3. Add the WhatsApp CTA button to the Facebook Page, which gives a free 72-h
   window.
4. Keep CSAT surveys sampled, or on the web only.

**Other costs:**

- Zambian hosting: get quotes.
- The blue badge is free if granted. Meta Verified is a paid subscription.
- Chatwoot is free software, but needs hosting and admin time.
- Staff time to answer handoffs. This is the largest real cost, and it exists
  today anyway.

---

## 9. Phased roadmap

Engineering estimates are for one developer and are **rough**. The Phase 0 items
have calendar lead times that engineering can't shorten, so start them today.

| Phase | Scope | Exit criteria | Rough size |
|---|---|---|---|
| **0. Decisions and paperwork** (in parallel, starting now) | The legal ruling on s.70/71 and the consent wording. ODPC registration check. IT-risk/CISO engagement. A bank-owned Meta Business portfolio and verification. The number decision. Zambian hosting procurement. The 24/7 fraud route decision. | Each item in §10 has an owner and an answer | Calendar time, weeks |
| **1. A channel-ready core** (no user-visible change) | Persistent sessions keyed by channel and user; `InboundMessage`; `render.py`; `short_label` across the content; per-channel limit tests; per-channel kill switches; the per-user limiter; hashed identities; bubble merging | The full suite is green, the web widget behaves the same, and the renderer test passes for every intent on every channel | 2–3 weeks |
| **2. WhatsApp pilot** | Webhooks (verification, signature, durable inbox, dedupe, stale handling); renderer; location-based locator; media policy; templates submitted; handoff option A (+B if coexistence). **Staff-only first** on the test number, then a limited public pilot. | Two weeks of staff use with no dead ends, and the weekly report broken down by channel | 2–3 weeks plus the pilot |
| **3. Messenger** | App Review; Get Started, persistent menu and ice breakers; conversation routing to the Page Inbox; private replies to urgent comments | Advanced Access granted; handoff tested end to end with the social team | 1–2 weeks plus the review wait |
| **4. Agent desk and optimisation** | Chatwoot self-hosted as the unified inbox (option C); move to the full API number and the blue badge; sampled CSAT; per-channel cost dashboard; optionally Instagram; optionally Bemba/Nyanja menus | Agents work from a single inbox, and time to first human response is measured | 3–4 weeks |
| **5. V2: a grounded LLM** | `app/llm.py` and `app/rag.py`, as the README already plans, but **only after the legal ruling**. Allowed under WhatsApp's January 2026 policy because it's AB Bank's own customer service. Fraud and complaint flows stay deterministic. | Legal sign-off; red-team suite passes | Separate plan |

---

## 10. Decisions needed from the bank

| # | Decision | Suggested owner |
|---|---|---|
| 1 | The lawful basis for Meta processing messages outside Zambia (s.70/71). The privacy notice and consent wording shown on first contact. | Legal / DPO |
| 2 | Who procures and owns production hosting in Zambia, given that IT isn't supporting the project but BoZ guidelines will likely require IT-risk sign-off | Management |
| 3 | The WhatsApp number: migrate 0769651262, use coexistence, or get a new number (§5.1) | Marketing + Contact Centre |
| 4 | Who answers handoffs on WhatsApp and Messenger, during which hours, to what SLA, and in which tool | Contact Centre / social team |
| 5 | What the fraud flow promises out of hours. This is the existing gap with no 24/7 card-block line, and an always-on channel makes it worse. | Operations / Risk |
| 6 | The wording of the three utility templates (§5.1) | Legal / Compliance |
| 7 | Confirming there will be no marketing messages at launch (ECT Act opt-in) | Marketing / Legal |
| 8 | A bank-owned Meta Business portfolio with at least two named bank admins | Management |
| 9 | Budget for WhatsApp fees, hosting and (optionally) Meta Verified | Finance |

---

## 11. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The data-localisation ruling delays launch | High | Start Phase 0 now, ask peer banks how they handled it, and build Phase 1 meanwhile (it's useful whatever the ruling) |
| Messenger App Review is rejected | Medium | Script the screencast to match the use case exactly, provide test credentials, and budget for a resubmission |
| Meta re-categorises templates as marketing (higher cost, and opt-in needed) | Medium | Neutral utility wording with no calls to action or promotional language |
| Customers are phished by fake "AB Bank" WhatsApp accounts | High | The blue badge, one official number published everywhere, and anti-scam lines in the bot and templates |
| Duplicate or days-late webhooks cause double replies or stale flows | Medium | Deduplicate on message ID, check timestamps, and write inbound messages durably before acking |
| The social team is swamped by handoffs | Medium | Clear hours, callback promises and routing by intent. Measure the handoff rate from week one. |
| Meta changes pricing again (it has changed it three times since 2024) | Low–Medium | Keep rates in config and compute cost per conversation in the weekly report |
| The account is restricted over quality or policy | High | Reply-only, no unsolicited sends, and a human path always visible |
| The single process is a single point of failure | Medium | Acceptable for the pilot with monitoring and backups. Redis/arq is the documented scale-out step. |
| The Meta assets end up owned by an individual or agency | High | A bank-owned portfolio with at least two bank admins, and a System User token |
| IT isn't involved, but it's a production bank channel | High | Raise it now. BoZ cyber-risk guidelines make an unsupported production channel hard to defend. |

---

## Appendix A: Platform limits

These are compiled from partner documentation. Check any value marked
**[VERIFY]** against Meta's docs.

| | WhatsApp (Cloud API) | Messenger | Website widget |
|---|---|---|---|
| Free-form reply window | 24 h from the user's last message | 24 h; +7 days for humans with `HUMAN_AGENT` | None |
| Outside the window | Templates only (utility / marketing / authentication) | Utility templates; marketing needs opt-in | n/a |
| Text length | 4,096 chars | 2,000 chars (button template text: 640) | Capped by `MAX_MESSAGE_CHARS` for input only |
| Tap-to-reply options | Reply buttons: ≤3, ≤20 chars | Quick replies: ≤13, ≤20 chars | Unlimited |
| Menus | List: ≤10 rows, row title ≤24 chars, optional description **[VERIFY 72]** | Persistent menu; button template ≤3 | n/a |
| Interactive body | ≤1,024 chars **[VERIFY]** | n/a | n/a |
| Location | Native location-request button → latitude/longitude | User can share location | Browser geolocation (optional) |
| Forms | WhatsApp Flows | Webview | Native |
| Webhook acknowledgement | `200` within seconds; retries up to 7 days | `200` within ~5 s | n/a (synchronous `/chat`) |
| Per-message cost | Service: 1,000 free per number per month, then the utility rate (from 1 Oct 2026) | None for customer service | None |

## Appendix B: Content audit (measured in this repo, 2026-09-23)

- **Intents:** 50 in total, 44 with static answers. The longest answer is 755
  characters (`business_account_requirements`). None exceeds WhatsApp's 1,024
  interactive-body limit. One exceeds Messenger's 640-character button-template
  limit.
- **Buttons per intent:** 3 buttons on 22, 4 on 13, 2 on 7 and 5 on 2. The
  remaining 6 have none because they start flows (fraud, lost card, complaint,
  handoff, and the branch and agent locators). The main menu has 5 buttons, so on
  WhatsApp the main menu and 15 answers need list messages.
- **Labels:** 37 of 81 distinct button and intent labels exceed 20 characters,
  for example "Transfer between eTumba and Airtel/MTN/Zamtel" (46). 22 exceed 24
  characters, so they don't fit a WhatsApp list row title either. Each needs a
  `short_label`.
- **Links:** 5 answers depend on links, which matters for customers on
  social-only bundles.
- **Branches:** 12 branches in 7 towns, which fits one WhatsApp list. They have
  no coordinates, which the location-based locator needs.
- **Bot messages per conversation**, measured by driving `router.handle()`:

| Path | Bubbles per turn | Bot messages in total |
|---|---|---|
| FAQ ("what is etumba" → "thanks") | 1, 1, 1 | 3 |
| Lost-card report (3 questions) | 1, **2**, 1, 1, 1 | 6 |
| Card number pasted in chat | 1, **2** | 3 |
| Callback request (4 questions) | 1, 1, 1, 1, 1, 1 | 6 |
| Branch locator (Lusaka) | 1, 1, 1, 1 | 4 |

The **2**s are where merging bubbles saves a billable WhatsApp message.

---

## 12. Sources

**Meta and WhatsApp platform (2025–26 changes)**

- [SendPulse: WhatsApp service message pricing changes, October 2026](https://sendpulse.com/blog/whatsapp-service-message-pricing)
- [360dialog: service message charging starts 1 October 2026](https://360dialog.com/blog/whatsapp-service-message-charging-october-2026/)
- [YCloud: service messages will be charged, 24-hour window cost guide](https://www.ycloud.com/blog/whatsapp-service-messages-24-hour-window-pricing)
- [ChakraHQ: non-template messages charged from October 2026](https://chakrahq.com/article/whatsapp-api-pricing-update-service-messages-october-2026)
- [Meta: upcoming pricing updates for Meta Business Agent, service and utility messages](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages)
- [Meta: pricing on the WhatsApp Business Platform](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)
- [WhAutomate: WhatsApp API pricing by country](https://whautomate.com/whatsapp-business-api-pricing)
- [Wati: message-based pricing (Rest of Africa region)](https://support.wati.io/en/articles/11561662-message-based-pricing-all-you-need-to-know)
- [Enterprise DNA: Meta Business Agent billing from 1 August](https://enterprisedna.co/resources/news/meta-business-agent-billing-august-1-token-pricing-2026/)
- [Tech Times: Meta Business Agent billing](https://www.techtimes.com/articles/320787/20260716/meta-business-agent-billing-starts-aug-1-free-test-window-ends-days.htm)
- [respond.io: not all chatbots are banned (WhatsApp 2026 AI policy)](https://respond.io/blog/whatsapp-general-purpose-chatbots-ban)
- [TechCrunch: WhatsApp rival-chatbot ban](https://techcrunch.com/2026/01/15/after-italy-whatsapp-excludes-brazil-from-rival-chatbot-ban)
- [Twilio changelog: WhatsApp usernames and BSUID](https://www.twilio.com/en-us/changelog/whatsapp-usernames--new-business-scoped-user-id--bsuid--field-re)
- [YCloud: usernames and business-scoped user IDs](https://www.ycloud.com/blog/whatsapp-usernames-and-business-scoped-user-ids)
- [Woztell: 2026 updates (pacing, limits, usernames)](https://woztell.com/whatsapp-api-2026-updates-pacing-limits-usernames/)
- [Chatarmin: WhatsApp messaging limits 2026](https://chatarmin.com/en/blog/whats-app-messaging-limits)
- [Meta: On-Premises API sunset](https://developers.facebook.com/docs/whatsapp/on-premises/sunset)
- [YCloud: WhatsApp Business app coexistence](https://www.ycloud.com/blog/whatsapp-business-app-coexistence-meta-update)
- [360dialog: coexistence](https://docs.360dialog.com/docs/resources/phone-numbers/coexistence)
- [Respond.io: phone number migration to Cloud API](https://respond.io/help/whatsapp/phone-number-migration-to-whatsapp-cloud-api)
- [Wati: WhatsApp verification and the blue tick](https://www.wati.io/en/blog/whatsapp-verification/)
- [Infobip: verify your WhatsApp Business Account](https://www.infobip.com/blog/verify-whatsapp-business-account)
- [WhatsApp Business Messaging Policy](https://whatsappbusiness.com/policy/)
- [Blip: human escalation policy in WhatsApp Business](https://help.blip.ai/hc/en-us/articles/4474389735191-Human-Escalation-Policy-in-WhatsApp-Business)
- [Meta: template categorisation](https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-categorization)
- [Infobip: WhatsApp interactive buttons](https://www.infobip.com/blog/how-to-use-whatsapp-interactive-buttons)
- [WOZTELL: WhatsApp Cloud message types](https://doc.woztell.com/docs/integrations/whatsapp/wa-message-types/)
- [360dialog: location request message](https://docs.360dialog.com/docs/messaging/message-types/interactive/location-request-message)
- [Courier: WhatsApp typing indicators](https://www.courier.com/blog/how-to-use-whatsapp-typing-indicators-on-twilio-public-beta-guide)
- [EngageLab: WhatsApp Flows](https://www.engagelab.com/blog/whatsapp-flows)
- [Hookdeck: guide to WhatsApp webhooks](https://hookdeck.com/webhooks/platforms/guide-to-whatsapp-webhooks-features-and-best-practices)
- [Meta: WhatsApp data privacy and security](https://developers.facebook.com/documentation/business-messaging/whatsapp/data-privacy-and-security/)
- [Meta: WhatsApp local storage](https://developers.facebook.com/documentation/business-messaging/whatsapp/local-storage/)
- [Vonage: WhatsApp local data storage](https://api.support.vonage.com/hc/en-us/articles/12605491997212-WhatsApp-Local-Data-Storage)
- [Respond.io: WhatsApp Business Calling API](https://respond.io/whatsapp-business-calling-api)

**Messenger**

- [Manychat: Meta's deprecation of Message Tags](https://community.manychat.com/product-updates/meta-s-deprecation-of-the-message-tags-feature-on-messenger-9010)
- [Chatwoot issue #14674: ACCOUNT_UPDATE tag deprecated](https://github.com/chatwoot/chatwoot/issues/14674)
- [Meta: Messenger Platform and Instagram Messaging API policy](https://developers.facebook.com/documentation/business-messaging/messenger-platform/policy)
- [Conferbot: Messenger chatbot guide 2026 (conversation routing)](https://www.conferbot.com/blog/messenger-chatbot-for-business)
- [WOZTELL: pass thread control](https://doc.woztell.com/docs/documentations/facebook/fb-pass-thread-control/)
- [Bottender: Messenger handover protocol](https://bottender.js.org/docs/channel-messenger-handover-protocol/)
- [Respond.io: Facebook private replies](https://respond.io/help/facebook-messenger/private-replies)
- [LivePerson: Messenger quick replies](https://developers.liveperson.com/facebook-messenger-templates-quick-replies-template.html)
- [Messenger bot App Review guide](https://singhamandeep.com/facebook-messenger-bot-app-review-chatbot-saas/)
- [Meta: webhooks for Messenger Platform](https://developers.facebook.com/documentation/business-messaging/messenger-platform/webhooks)
- [TechCrunch: Meta shutting down Messenger's website](https://techcrunch.com/2026/02/19/meta-is-shutting-down-messengers-standalone-website/)
- [TechCrunch: Messenger desktop apps shut down](https://techcrunch.com/2025/10/16/meta-to-shut-down-messenger-desktop-apps-for-mac-and-windows/)
- [Respond.io: Facebook chat plugin deprecation](https://respond.io/help/facebook-messenger/facebook-chat-plugin)

**Zambia: law, regulation, market**

- [Data Protection Act 2021 (ZambiaLII)](https://zambialii.org/akn/zm/act/2021/3/eng@2021-03-24)
- [CIPESA: insights into Zambia's Data Protection Act](https://cipesa.org/insights-into-zambias-data-protection-act-2021/)
- [Securiti: Zambia DPA overview](https://securiti.ai/zambia-data-protection-act-dpa/)
- [ITLawCo: ODPC registration deadline](https://itlawco.com/zambias-odpc-registration-deadline-30-april-2025/)
- [Bowmans: ODPC operational](https://bowmanslaw.com/insights/zambia-office-of-the-data-protection-commissioner-operational/)
- [Data Protection Commission, Zambia](https://www.dataprotection.gov.zm/)
- [Bowmans: Zambia's new cyber laws](https://bowmanslaw.com/insights/zambia-new-laws-to-strengthen-cybersecurity-and-cybercrime-capacities/)
- [Cyber Security Act 2025 (ZambiaLII)](https://zambialii.org/akn/zm/act/2025/3/eng@2025-04-15)
- [Mpelembe: impact of Zambia's 2025 cyber laws](https://mpelembe.net/index.php/securing-the-cyberspace-the-impact-of-zambias-2025-cyber-laws-on-security-and-civil-liberties/)
- [Bank of Zambia: Cyber and Information Risk Management Guidelines 2023](https://www.boz.zm/BankofZambiaCyberandInformationRiskManagementGuidelinesGazetted31May2023.pdf)
- [Bank of Zambia: Customer Complaints Handling and Resolution Directives](https://www.boz.zm/BankofZambiaCustomerComplaintsHandlingandResolutionDirectives1.pdf)
- [DLA Piper: electronic marketing in Zambia](https://www.dlapiperdataprotection.com/countries/zambia/electronic-marketing.html)
- [ECT Act 2021 (ZambiaLII)](https://zambialii.org/akn/zm/act/2021/4)
- [DataReportal: Digital 2026 Zambia](https://datareportal.com/reports/digital-2026-zambia)
- [Yazi: WhatsApp penetration across Africa](https://www.askyazi.com/articles/whatsapp-penetration-across-africa-statistics-by-country)
- [ZamCompare: cheapest WhatsApp and Facebook bundles 2026](https://zamcompare.com/cheapest-whatsapp-facebook-data-bundles/)
- [CLEAR Global: language data for Zambia](https://clearglobal.org/language-data-for-zambia/)
- [Datacentermap: Lusaka data centres](https://www.datacentermap.com/zambia/lusaka/)
- [Paratus: data centre services](https://paratus.africa/services/data-center-services/)
- [Zanaco: launch of WhatsApp Banking](https://www.zanaco.co.zm/2026/05/08/launch-of-zanaco-whatsapp-banking-chat-transact/)
- [Zanaco: WhatsApp Banking FAQs](https://www.zanaco.co.zm/whatsapp-banking-faqs/)
- [Stanbic Zambia: AI-powered social media chatbot](https://www.stanbicbank.co.zm/zambia/personal/about-us/news/STANBIC-TALKS-HIGH%E2%80%93TECH-WITH-NEW-AI-POWERED-SOCIAL-MEDIA-CHATBOT)
- [Techtrends Zambia: Stanbic launches Stan](https://www.techtrends.co.zm/stanbic-bank-zambia-launches-stan-ai-powered-social-media-bot/)

**Best practice, examples and tooling**

- [CFPB: chatbots in consumer finance](https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/)
- [NN/g: 10 guidelines for designing AI chatbots](https://www.nngroup.com/articles/ai-chatbots-design-guidelines/)
- [Absa: customers embrace ChatBanking on WhatsApp](https://www.absa.co.za/media-centre/press-statements/2018/absa-customers-embrace-chatbanking-on-whatsapp/)
- [UBA Ghana: banking on WhatsApp and Facebook](https://www.ubaghana.com/media/news-events/uba-makes-history-by-introducing-banking-on-whatsapp-and-facebook/)
- [Kolonell: WhatsApp voice-note bots (voice-note prevalence)](https://kolonell.com/en/blog/whatsapp-voice-message-bot-2026-en)
- [Chatwoot: agent bots](https://www.chatwoot.com/hc/user-guide/articles/1677497472-how-to-use-agent-bots)
- [Chatwoot: API channel inbox](https://www.chatwoot.com/hc/user-guide/articles/1677839703-how-to-create-an-api-channel-inbox)
- [Chatwoot issue #8288: WhatsApp interactive button limits](https://github.com/chatwoot/chatwoot/issues/8288)
- [pywa (PyPI 4.4.0, verified 2026-09-23)](https://github.com/yehuda-lev/pywa)
- [Gurusup: WhatsApp BSP comparison 2026](https://gurusup.com/blog/whatsapp-api-bsp-providers)
- [Kommunicate: Twilio vs 360dialog](https://www.kommunicate.io/blog/twilio-vs-360dialog-a-comparison/)
