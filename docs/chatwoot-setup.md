# Agent desk (Chatwoot): setup and agent notes

Tickets H2 (agent desk) and H4 ("bot got this wrong" loop). This is the
hand-over document for IT, who install Chatwoot, and for the contact centre,
whose agents use it. The code side is in `app/desk/` and
`admin/export_bot_wrong.py`.

## Summary

- When a **WhatsApp** customer taps "Talk to a person", the bot creates the
  handoff ticket (and so the Jira issue) as before, then opens a conversation
  in a self-hosted Chatwoot and goes quiet. An agent replies in Chatwoot and
  the reply reaches the customer on WhatsApp. When the agent resolves the
  conversation, the bot takes over again.
- **Messenger** keeps its native Page Inbox handover (M4) for now. The
  **website** keeps tickets and callbacks; it can join the desk later as live
  chat.
- **Jira stays the system of record** for fraud reports, complaints and
  callbacks. Chatwoot is where agents talk to customers, not where cases are
  tracked.
- Chatwoot never receives a phone number, WhatsApp id or platform id. The
  contact is identified by `user_hash` (an HMAC, see `app/identity.py`) and
  every text sent to it is masked.
- With the Chatwoot settings unset, nothing changes: WhatsApp's "Talk to a
  person" stays the callback flow.

Everything below marked **[VERIFY]** comes from Chatwoot's public
documentation, not from a running instance. Check it on the installed
version before go-live.

## 1. What IT installs

**Software:** Chatwoot, self-hosted, **Community edition**. The Chatwoot
repository is MIT-licensed except for its `enterprise/` folder, which has
its own licence **[VERIFY the licence of the edition and version actually
installed, and that no Enterprise-only feature is switched on]**. We use
only Community features: inboxes, agents, labels, private notes, custom
attributes, webhooks and the Application API.

**Where:** a **second VM** in Lusaka, next to the chatbot VM (P7), not on
it. Chatwoot runs its own Rails app, background workers, PostgreSQL and
Redis; keeping it separate means a desk problem cannot take the bot down.

| Item | Suggested | Notes |
|---|---|---|
| CPU | 2 vCPU | Chatwoot's documented minimum **[VERIFY]** |
| Memory | 4 GB, 8 GB preferred | **[VERIFY]** against Chatwoot's current requirements |
| Disk | 40 GB SSD, plus backups | Grows with conversations and attachments |
| OS | Ubuntu LTS | Docker Compose or Chatwoot's Linux install script **[VERIFY supported versions]** |
| Network | HTTPS only (TLS on a reverse proxy) | Agents' browsers reach it; the chatbot VM reaches its API; it reaches the chatbot's webhook |
| Email | An SMTP relay | For agent invitations and password resets |
| Backups | Nightly PostgreSQL dump, kept per the retention policy | **[CONFIRM retention with Legal]** |

Access rules:
- Agents reach Chatwoot from the bank network (or VPN) only
  **[CONFIRM with IT Security]**.
- The chatbot VM must reach `CHATWOOT_URL`; Chatwoot must reach the
  chatbot's public URL for the webhook.
- Turn off public sign-up on the Chatwoot instance **[VERIFY setting name]**.
- Switch on two-factor authentication for agents if the installed version
  offers it **[VERIFY]**.

## 2. One-off configuration in Chatwoot

Do these as a Chatwoot **administrator**.

### 2.1 The API-channel inbox

1. **Settings → Inboxes → Add Inbox → API** **[VERIFY menu names]**.
2. Name it `WhatsApp (via assistant)`. Leave its own webhook URL empty: we
   use the account webhook in 2.4.
3. Add the agents who handle WhatsApp handoffs to the inbox.
4. Note the inbox id (it is in the address bar on the inbox's settings
   page): this is `CHATWOOT_INBOX_ID`.

Why an API channel and not Chatwoot's own WhatsApp channel: the bot keeps
the connection to Meta, so its buttons, guards and audit trail stay in
charge, and Chatwoot only sees what we choose to send it (research §7.6).

### 2.2 Agents

- One Chatwoot account per contact centre agent, named as in the staff
  directory, role **Agent**. Team leads get **Administrator** only if they
  manage settings.
- Remove leavers the same day, as for any other bank system.

### 2.3 Labels and custom attributes

- **Label `bot-wrong`** (exactly this, lower case). Agents add it when the
  assistant misunderstood the customer. H4 reads it every week.
- **Conversation custom attributes** `ticket_ref`, `jira_key` and `channel`
  (type text). The bot fills them on every handoff. Defining them in
  **Settings → Custom Attributes** makes them show neatly in the sidebar
  **[VERIFY whether values set through the API appear without a definition]**.

### 2.4 The webhook back to the bot

1. Generate a long random secret, at least 24 characters (shorter ones are
   refused and the route answers 404). For example:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. **Settings → Integrations → Webhooks → Add** **[VERIFY menu names]**:
   - URL: `https://<chatbot host>/webhooks/chatwoot/<secret>`
   - Events: **Message created** and **Conversation status changed**.
     Nothing else is needed.
3. The same secret goes into `CHATWOOT_WEBHOOK_SECRET` on the chatbot VM.

Chatwoot's webhooks carry no signature **[VERIFY for the installed
version]**, so the secret in the path is what proves a call came from our
Chatwoot. The bot compares it in constant time and answers 403 to a wrong
one. Treat the URL like a password: do not paste it into tickets or chats,
and rotate it (new secret in both places) if it leaks.

### 2.5 The API token

The bot acts in Chatwoot as one user. Create a dedicated agent such as
`Assistant (system)`, add it to the inbox, and copy its access token from
**Profile settings → Access token**: this is `CHATWOOT_API_TOKEN`
**[VERIFY that this token type may create contacts, conversations and
incoming messages on the installed version; an agent-bot token may be the
better fit]**. The account id is the number after `/app/accounts/` in the
address bar: `CHATWOOT_ACCOUNT_ID`.

## 3. Chatbot settings

Set these in the chatbot's environment (never in `flags.json` or git). All
four of URL, account, inbox and token are needed; with any one missing the
desk is off.

| Variable | What it is |
|---|---|
| `CHATWOOT_URL` | Base address, e.g. `https://desk.example.zm` (no trailing path) |
| `CHATWOOT_ACCOUNT_ID` | From 2.5 |
| `CHATWOOT_INBOX_ID` | From 2.1 |
| `CHATWOOT_API_TOKEN` | From 2.5 |
| `CHATWOOT_WEBHOOK_SECRET` | From 2.4, 24+ characters |
| `DESK_IDLE_HOURS` | Optional, default 24: with no agent reply for this long, the bot answers the customer again |
| `CHATWOOT_ENABLED` | Kill switch (env or `flags.json`, default on). `false` sends **new** WhatsApp handoffs back to the callback flow at once, e.g. during a Chatwoot outage; conversations already on the desk carry on |

Restart the chatbot after changing the four connection settings. The kill
switch takes effect without a restart, like the others.

Housekeeping: the bot keeps one small table, `data/desk.db`, mapping a
Chatwoot conversation to a hashed session key and ticket reference. It is
created on first use and purged on the `TRANSCRIPT_RETENTION_DAYS` schedule.

## 4. How a handoff works

1. The customer taps "Talk to a person" on WhatsApp. The bot creates the
   handoff ticket and the Jira issue, as before.
2. The bot finds or creates the Chatwoot contact (identifier `user_hash`,
   plus a name only if the customer typed one in a flow), opens a
   conversation in the inbox with status *open* and the ticket reference and
   Jira key as custom attributes, then posts a **private note**: case
   reference, Jira key, until when a free reply is possible (Lusaka time),
   and the conversation so far with personal details masked.
3. The bot pauses. Every message the customer sends appears in the
   conversation as theirs (masked, and phone numbers replaced by
   `[PHONE REDACTED]`).
4. An agent's public reply is sent to the customer on WhatsApp and resets
   the idle timer.
5. The agent **resolves** the conversation: the bot takes over again.
6. If no agent replies for `DESK_IDLE_HOURS`, the customer's next message is
   answered by the bot and a private note says so.

If Chatwoot is down at step 2, the bot is **not** paused, so the customer is
never left talking to nobody. The ticket is already in Jira and staff follow
up from `/admin/cases`. Every failure is logged as an audit event
(`desk_failed`, `desk_forward_failed`, `desk_note_failed`,
`desk_send_failed`, `desk_window_closed`, `desk_unlinked`) for alerting.

## 5. Agent training notes (contact centre)

For the W19 training session. Keep it to these points.

- **Read the private note first.** It has the case reference, the Jira key
  and what the customer already told the assistant. Do not ask them to
  repeat it.
- **Personal details are masked on purpose.** You will see `[CARD
  REDACTED]`, `[PHONE REDACTED]` and similar. You do not get the customer's
  WhatsApp number in Chatwoot. If you need to call them, use the contact
  details in the Jira ticket, where the customer gave them.
- **Never ask for a PIN, password, OTP or full card number**, in Chatwoot
  or anywhere else. The assistant masks them if a customer sends them
  anyway.
- **Private notes stay private.** Use a private note for anything meant for
  colleagues; only public replies reach the customer.
- **Text only.** Attachments are not sent to customers from the desk; a
  note tells you if you try.
- **The 24-hour rule.** WhatsApp lets us reply freely only within 24 hours
  of the customer's last message. After that your reply is **not sent** and
  a private note tells you so. Send the `case_update` template from
  `/admin/cases` instead.
- **Resolve when you have finished.** That hands the customer back to the
  assistant. An unresolved conversation keeps the assistant quiet until the
  idle fallback (24 hours without a reply from you).
- **Jira is the record.** Update the Jira issue for fraud reports,
  complaints and callbacks as you do today. Chatwoot is the conversation,
  not the case file.
- **Tag the assistant's mistakes.** If the assistant misunderstood the
  customer before handing over, add the label **`bot-wrong`** to the
  conversation (or to the Jira issue). Those messages go to the weekly
  labelling review and make the assistant better. Do not add notes with
  customer details to explain why; the label is enough.

## 6. The "bot got this wrong" loop (H4)

`admin/export_bot_wrong.py` runs weekly. It:

1. pulls Chatwoot conversations labelled `bot-wrong` with activity in the
   last 7 days, and Jira issues with the `bot-wrong` label updated in the
   same period (JQL). A source that is not configured is skipped;
2. keeps only the customer's turns (the `[user]` lines of the handoff note
   or Jira description, and the customer's messages to the agent);
3. drops button taps and anything that still looks personal, with the same
   second PII check as `admin/export_utterances.py`;
4. appends what is new to `data/utterances.csv` with `source=bot-wrong`,
   skipping any text already in the file.

The rows then follow the normal N1 flow: two reviewers fill `label_a` and
`label_b`, then `python -m admin.import_labels data/utterances.csv`. The
script prints counts only, never message text, and exits non-zero if a
source failed (so cron mails the output).

Cron line, after the export of audit utterances (which rewrites the CSV)
and next to the H6 weekly report:

```
15 6 * * 1  cd /opt/abz-chatbot && .venv/bin/python -m admin.export_bot_wrong --days 7
```

Adjust the path to the installed location (P7).

## 7. Before go-live checklist

- [ ] Licence of the installed Chatwoot edition checked **[VERIFY]**.
- [ ] Every **[VERIFY]** in this file and in `app/desk/chatwoot.py` checked
      against the installed version (one test conversation end to end).
- [ ] Webhook secret set in both places; a wrong secret returns 403.
- [ ] A test handoff shows no phone number or WhatsApp id anywhere in
      Chatwoot (contact, conversation, notes).
- [ ] An agent reply after 24 hours is refused with the note.
- [ ] Resolving resumes the bot.
- [ ] Agents trained (section 5) and the `bot-wrong` label in use.
- [ ] Backups and retention agreed **[CONFIRM with Legal and IT]**.
