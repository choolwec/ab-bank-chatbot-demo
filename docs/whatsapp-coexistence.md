# WhatsApp coexistence pause (ticket W11)

Status: built, **off by default** (`COEXISTENCE_ENABLED=false`) until the
WhatsApp number decision is confirmed. Draft for review; the items marked
[VERIFY] must be checked against Meta's current documentation before the flag
is turned on.

## Summary

Decision D5 (`docs/decisions-log.md`) chose option B for the WhatsApp pilot:
**coexistence**. Staff keep using the WhatsApp Business app on the official
number, and the bot runs on the Cloud API alongside them
(`docs/multi-platform-research.md` §5.1 and §7.6). Two writers on one number
means two replies can collide. W11 stops that: when a staff member replies to a
customer from the app, the bot goes quiet for that customer. It comes back after
`COEXISTENCE_PAUSE_HOURS` (default 12) with no further staff reply, or as soon
as the customer asks for the menu. A fraud or lost-card report from a paused
customer is never lost: it still becomes a fraud ticket and a Jira issue.

## How staff and the bot share the number

| Who writes | What happens |
|---|---|
| Customer writes, no staff reply yet | The bot answers as usual. Staff can see the chat in the Business app. |
| A staff member replies from the Business app | Meta sends an `smb_message_echoes` webhook. The bot pauses for that customer only. Other customers are unaffected. |
| Customer writes while paused | No bot reply. The message is logged, masked, as usual. Staff answer from the app. |
| Staff reply again | The pause timer restarts from that reply. |
| 12 hours pass with no staff reply, or the customer types or taps "menu" | The bot answers again, starting with the menu if they asked for it. |

Practical guidance for staff:

- Replying to a customer is enough to take over; there is no button to press.
- If you finish helping a customer and want the bot back sooner, ask the
  customer to type **menu**.
- Messages you send are never stored by the bot. Only the fact that a person
  replied, and when, is recorded.
- The bot's own messages do not appear to pause itself (see [VERIFY] below).

## How it works

1. **Webhook.** `POST /webhooks/whatsapp` checks `X-Hub-Signature-256` over the
   raw body exactly as for every other event (401 on failure, nothing stored).
   `whatsapp.parse_echo()` turns each `message_echoes` item into an
   `InboundMessage` with `kind="echo"`, keyed by the **customer** the reply
   went to (the BSUID when present, else the `wa_id`, the same key as the
   customer's own messages). The staff member's text is dropped at parse time.
2. **Durable inbox and worker.** The echo is stored in `inbox.db` before the
   200 is returned, de-duplicated by its message id (`whatsapp:echo:<wamid>`),
   and processed in order by the single worker.
3. **Pause.** `app/channels/coexistence.py` `handle_echo()` sets
   `session.bot_paused_until` (the same pause the agent desk and Messenger use,
   through `messenger.pause()`) to the staff reply's time plus
   `COEXISTENCE_PAUSE_HOURS`, and marks `slots["coexistence_paused_at"]`. An
   echo never shortens a longer pause (for example an agent-desk pause). An
   echo that arrives after its pause would already have ended (a late Meta
   redelivery) is logged as `human_reply_echo_stale` and ignored. An echo does
   not open or extend the customer's 24-hour window.
4. **While paused.** `messaging.py` step 4, unchanged in shape: the customer's
   message is logged (already masked by `inbox.py`) with `action=paused`, and
   nothing is sent.
5. **Resume.** On the customer's next message, `coexistence.expire()` lifts the
   pause if the timer has run out (`coexistence_resumed`, reason "timeout"),
   and `coexistence.resume_on_menu()` lifts it when the whole message is a
   menu command (`router.COMMANDS`: "menu", "main menu", "0", "start again"
   and so on) or the Main menu button. "menu" inside a sentence does not count.
   If an agent-desk conversation is also open, the desk's own pause applies.

## Unfinished reports

If a fraud report or complaint is in progress when a staff member replies, its
collected data goes straight onto a ticket of the same type (with
`unfinished: yes`), and the flow is closed, as the handoff to the inbox does.
Otherwise the customer's answers during the pause would never reach the flow,
and the report could expire unseen.

## Urgent messages while paused

A paused customer who sends a **hard** fraud or lost-card signal
(`guards.urgent_scan`, strength "hard", kind "fraud") gets:

- a **fraud ticket** (`audit.create_ticket`, which also pushes the Jira issue)
  with the masked message as `what_happened`, the masked transcript, and
  `reported_while: staff_replying_in_business_app`;
- an audit event `coexistence_urgent` with the ticket reference;
- **one short safety reply** (`coexistence.urgent_safety` in
  `knowledge/system_messages.yaml`, status draft): the reference, the emergency
  number, and "never share your PIN", with a Main menu button.

This happens once per pause. Later urgent messages in the same pause are logged
(`coexistence_urgent_repeat`) and appear in the staff member's chat, but raise
no second ticket and no second reply. Soft signals (questions about scams,
"money missing" and so on) are only logged; staff see them in the app.

Why send a reply at all, when the pause exists to avoid collisions: a lost card
or live fraud needs the card blocked within minutes, and the staff member who
last replied may be busy, off shift, or away from the phone. One clearly
labelled automated message, at most once per pause, costs little in collision
terms and tells the customer the fastest route. Ops/Risk should confirm the
wording and the emergency number (still `[CONFIRM]` in `app/config.py`).

The agent-desk (H2) and Messenger (M4) pauses are unchanged: there, urgent
messages are forwarded to the person, as before.

## Flag and settings

| Setting | Default | Where | Effect |
|---|---|---|---|
| `COEXISTENCE_ENABLED` | `false` | `flags.json` (env var overrides) | Off: echoes are logged as `human_reply_echo_ignored` and nothing else changes. A pause already running is lifted on the customer's next message (`coexistence_resumed`, "coexistence switched off"). |
| `COEXISTENCE_PAUSE_HOURS` | `12` | env var (`deploy/env.example`) | Hours of quiet after each staff reply. A value that is not a positive number falls back to 12. |

Use `flags.json` for the switch, as for every kill switch; a value in the
production env file overrides it and needs a restart to change.

## Audit events

All carry `channel` and `user_hash` only: no message text from staff, no phone
number, no `wa_id` or BSUID.

| Action | When |
|---|---|
| `human_reply_echo` | A staff reply paused (or re-paused) the bot. |
| `human_reply_echo_ignored` | An echo arrived with the flag off. |
| `human_reply_echo_stale` | A late echo whose pause had already ended. |
| `paused` | A customer message arrived while paused (the message itself is logged, masked, as a `user` event). |
| `coexistence_resumed` | The pause ended: timeout, menu, or flag switched off. |
| `coexistence_urgent` / `coexistence_urgent_repeat` | A hard urgent message while paused: ticket raised / already raised. |
| `coexistence_unfinished_ticket` | A report in progress was ticketed when staff took over. |

## [VERIFY] before turning the flag on

1. **The echo payload shape.** Modelled as a `smb_message_echoes` change whose
   `value.message_echoes[]` items carry `from` (our number), `to` (the
   customer's `wa_id`), optionally `to_user_id` (a BSUID), `id`, `timestamp`
   and `type`. The recorded sample is `tests/data/wa/echo.json`. Confirm the
   field names against Meta's coexistence webhook reference, and subscribe the
   app to the `smb_message_echoes` field.
2. **Whether Meta sends echoes for app-sent messages in coexistence**, and only
   for those. The design assumes echoes come for messages typed in the
   Business app (and its linked devices), and **not** for messages the bot
   sends through the Cloud API. If API sends were also echoed, the bot would
   pause itself after every reply; test this on the staff test number first.
3. **The 13-day app-open rule.** Research (§5.1) says the Business app must be
   opened at least every 13 days or coexistence may be disconnected. Confirm
   the current rule and give someone in the Contact Centre the job of opening
   it; a disconnection would stop the bot and the app sharing the number.

## Other open points

- Staff replies are only detected through echoes. A staff member who reads a
  chat but does not reply does not pause the bot.
- A staff member who replies more than 12 hours after their last reply, while
  the customer has been talking to the bot, pauses it again from that moment.
- Media and location messages from a paused customer are logged only (no
  safety reply); only text is scanned for urgent signals.

## Tests

`tests/test_coexistence.py` (all mocked, no network): an echo pauses the bot;
messages while paused get no reply and are logged masked; an urgent message
while paused still creates a fraud ticket and Jira issue, once; resume after
the timeout and on "menu" (typed and tapped); a new echo extends the pause;
flag off changes nothing; a bad signature is rejected; no raw number, `wa_id`
or staff text is stored anywhere.
