# Incident runbook (ticket R1)

For Dev, the PO and the Contact Centre (CC) lead. Written 24/09/2026.

**In short:** the app checks itself (`/health`), a cron job turns a failing
check into a card in the **Chatbot alerts** Teams group chat and a Jira issue,
and this page says what each alert means and what to do first. Out of hours,
nobody changes code: the PO or CC lead uses a **kill switch** (§4) and Dev
picks it up next working morning.

Paths and names below (`/opt/abz-chatbot`, service `abz-chatbot`, user `abz`,
`/etc/abz-chatbot/env`) follow the production plan (P7). Check them against
`deploy/` once P7 lands. Items marked **[CONFIRM]** need a decision from the
bank; **[VERIFY]** items must be checked against the vendor's current screens.

---

## 1. Severity levels

| Severity | Examples | First response |
|---|---|---|
| **Sev 1** | A fraud report not routed; PII in logs; a wrong fee quoted | Kill switch (`FREE_TEXT_ENABLED=false` or channel off) within 15 minutes, notify PO and Compliance, fix, write a post-mortem |
| **Sev 2** | Channel outage; webhook failures; Meta quality rating drops | Fix within 1 working day |
| **Sev 3** | A wrong-but-safe answer | Next content release |

Anyone who spots a Sev 1 (a customer, a CC agent, a reviewer, an alert) posts
it in the Chatbot alerts chat straight away, even if unsure. Downgrading later
costs nothing.

## 2. Automatic alerts

`python -m admin.alerts` runs every minute (§6). It reads the app's `/health`
and sends each failing check to **Teams** (the Chatbot alerts group chat) and
**Jira** (label `chatbot-alert`).

| Alert | Fires when | Severity | First step |
|---|---|---|---|
| `health_down` | `/health` fails 3 tries, 10 s apart (so a restart during a deploy is not reported), or answers anything but 200 | **Sev 1**: nothing answers on any channel, fraud reports included | `sudo systemctl status abz-chatbot`, then `journalctl -u abz-chatbot -n 200`; restart. While down, the widget hides itself and WhatsApp/Messenger customers get no reply. |
| `flags_file` | `flags.json` is not valid JSON, or a value is not `true`/`false` | **Sev 1**: every kill switch is silently back at its default | Fix the file now (§4, step 3). |
| `failed_messages` | Any webhook message failed all 5 attempts in the last hour | **Sev 2**; **Sev 1** if one reads as a fraud report | These customers got no reply. Find the error in the service log and fix it. For Sev 1, tell the CC lead so the contact centre can watch for the customer calling in. |
| `worker_queue` | The oldest waiting webhook message is older than 2 minutes | Sev 2 | The inbox worker is stuck. Look for `inbox processing failed` in the log; restart. Waiting messages are kept and answered in order. |
| `send_failures` | More than 2% of replies to Meta failed in the last hour | Sev 2 | Look for `send failed` in the log and check Meta's status page. HTTP 401/403 usually means an expired `WA_ACCESS_TOKEN` or `MS_PAGE_TOKEN`. If nothing gets through, switch that channel off. |
| `webhook_errors` | More than 1% of `/webhooks/*` requests got a 5xx in the last hour | Sev 2 | Tracebacks in the log. Meta retries, so fix and restart; if it persists, switch the channel off. |
| `webhook_rejected` | More than 2 requests carrying Meta's signature were refused (4xx) in the last hour | Sev 2 | Almost always a wrong or rotated `WA_APP_SECRET` / `MS_APP_SECRET`. Compare with the Meta app dashboard; restart. |
| `jira_backlog` | A ticket's Jira copy has been owed for more than 30 minutes (real Jira only; failed pushes are retried every 5 minutes, backing off, for 24 hours) | Sev 2: the ticket is safe in the bot but the contact centre can't see it in Jira | Check the service log and Jira; a 401/403 usually means an expired `JIRA_API_TOKEN`. After 24 hours a ticket is given up (audit action `jira_push_abandoned`): copy it into Jira by hand from `/admin/cases`. |
| `embedding_model` | The local model did not verify while a feature needs it (`URGENT_MODEL_ENABLED` is on by default) | Sev 2: the second fraud check is off; the keyword rules still work | `.venv/bin/python -m admin.fetch_model`, then restart. |

Notes:
- **Low volumes.** At pilot volumes a single failure can exceed 1% or 2%. That
  is intended: while traffic is low, every failure is worth a look.
- **Counters restart with the app.** Send and webhook counts are kept in
  memory, so a restart starts a new hour.
- **Sev 3 has no automatic alert.** Wrong-but-safe answers come from the
  weekly report, transcript reviews and CC feedback.

### How often you hear about it

- **Teams:** the first post when an issue starts, then at most one reminder
  per issue every **15 minutes** while it lasts, then one green **Resolved**
  post when it clears. A rise in severity (failed messages that turn out to
  include a fraud report) is posted at once.
- **Jira:** at most one issue per alert per **24 hours**. The script never
  closes Jira issues; the person who fixes it does (for Sev 1, once the
  post-mortem is written).
- A card shows: severity, what is wrong, the value now, the threshold, since
  when, the environment (`ALERT_ENV_NAME`, so staging and production can share
  the chat) and the first step. Never a customer id, a phone number or message
  text.

### Reading `/health` yourself

`curl -s http://127.0.0.1:8000/health` on the VM, or the public URL from
outside. HTTP stays 200 when a check fails; only an app that cannot read its
own stores answers 503. Every check has `ok`; uptime checkers read
`checks.<name>.ok`.

```json
{
  "status": "ok", "version": "0.1.0", "free_text_enabled": true, "widget_enabled": true,
  "checks": {
    "worker_queue":     {"ok": true, "oldest_pending_seconds": 0, "pending": 0, "threshold_seconds": 120},
    "failed_messages":  {"ok": true, "count": 0, "urgent": 0, "threshold": 0, "window_minutes": 60},
    "send_failures":    {"ok": true, "attempts": 42, "failed": 0, "rate": 0.0, "threshold": 0.02, "window_minutes": 60, "by_channel": {}},
    "webhook_errors":   {"ok": true, "requests": 57, "count_5xx": 0, "count_4xx": 1, "rate": 0.0, "threshold": 0.01, "window_minutes": 60},
    "webhook_rejected": {"ok": true, "count": 0, "threshold": 2, "window_minutes": 60},
    "embedding_model":  {"ok": true, "verified": true, "needed_by": ["URGENT_MODEL_ENABLED"]},
    "jira_backlog":     {"ok": true, "active": true, "pending": 0, "oldest_pending_minutes": 0, "threshold_minutes": 30},
    "flags_file":       {"ok": true, "readable": true, "invalid": []}
  }
}
```

**[CONFIRM]** which uptime checker watches the public `/health` from outside
the bank's network (P7 acceptance asks for it). Alert on a non-200 or on any
`"ok": false`.

## 3. First steps per severity

### Sev 1

1. **Contain within 15 minutes.** Pick the kill switch (§4):
   - wrong or harmful answers to typed questions: `FREE_TEXT_ENABLED` false;
   - one channel misbehaving: `WHATSAPP_ENABLED`, `MESSENGER_ENABLED` or
     `WIDGET_ENABLED` false;
   - the whole app down: restart it (`health_down` above). A kill switch cannot
     help while the app is down.
2. **Notify** the PO and Compliance **[CONFIRM: Compliance contact and
   channel]** in the Chatbot alerts chat or by phone.
3. **PII in logs:** do not delete anything until Compliance says so; they
   decide whether the Data Protection Act requires a notification **[CONFIRM
   with Legal/Compliance: obligations and deadlines]**. Note which files and
   dates are affected (`data/audit.db`, `data/audit.jsonl`, the service log,
   Jira).
4. **Fix** in business hours (Dev), with a test that would have caught it,
   and the full suite green.
5. **Switch back on** only after the fix is deployed and checked.
6. **Post-mortem** (§8) within 5 working days **[CONFIRM the deadline]**.

### Sev 2

1. Out of hours: switch the affected channel off only if customers are getting
   wrong or no answers; otherwise leave it for Dev.
2. Dev fixes within 1 working day and notes the cause in the Jira issue.
3. If a Meta quality rating dropped, the PO reviews the templates and recent
   complaints with the CC lead before sending more templates.

### Sev 3

Record it in Jira with the conversation reference (ticket or session id, never
the customer's number) and fix it in the next content release. Content edits
are deploys: the full suite must pass.

## 4. Kill switches: exact steps

Kill switches take effect **without a restart** when set in `flags.json`,
which the app re-reads on every check. An environment variable wins over
`flags.json` but needs a restart to change.

**Using `flags.json` (preferred, immediate):**

1. Log in to the VM and go to the app folder: `cd /opt/abz-chatbot`.
2. Edit `flags.json` (`nano flags.json`) and set the switch, for example:

   ```json
   {
     "FREE_TEXT_ENABLED": false,
     "WIDGET_ENABLED": true,
     "JIRA_ENABLED": true
   }
   ```

   Write `true` or `false` **without quotes**. `"false"` in quotes is ignored
   and the switch stays **on**.
3. Check the file: `python3 -m json.tool flags.json`. It prints the file back
   if it is valid, or shows the line with the error. A broken file puts every
   switch back to its default; the `flags_file` alert fires within a minute.
4. Confirm it took effect:
   - `curl -s http://127.0.0.1:8000/health` shows `free_text_enabled` and
     `widget_enabled`, and `checks.flags_file.ok` should be `true`;
   - for other switches:
     `.venv/bin/python -c "from app import config, urgent_model; print(config.channel_enabled('whatsapp'), config.channel_enabled('messenger'), urgent_model.enabled())"`.
5. Post in the Chatbot alerts chat what you switched and when.

**Using an environment variable (a restart):** add, for example,
`FREE_TEXT_ENABLED=false` to `/etc/abz-chatbot/env`, then
`sudo systemctl restart abz-chatbot`. While a switch is set there, editing it
in `flags.json` does nothing, so keep kill switches out of the env file unless
the setting is meant to stay.

**After a deploy**, check `flags.json` again: a deploy may bring back the
committed version **[CONFIRM against `deploy/deploy.sh`, P7]**. Commit a
switch that must stay off.

| Switch | Default | Off means | Takes effect |
|---|---|---|---|
| `FREE_TEXT_ENABLED` | on | Typed questions get "Free-typing is temporarily unavailable" and the menu. Buttons, flows and the fraud/complaint wording scan keep working. | At once |
| `WIDGET_ENABLED` | on | `/chat` answers 503 and the widget stays hidden on the next page load (it checks `/health` when a page opens). | At once; open pages on reload |
| `WHATSAPP_ENABLED` | on | Each customer gets one fixed message pointing to the Contact Centre and the emergency number, at most once an hour. Messages are still logged. | At once |
| `MESSENGER_ENABLED` | on | The same, on Messenger. | At once |
| `URGENT_MODEL_ENABLED` | on | The model-based second fraud check stops. The keyword rules still catch fraud reports. | At once |
| `EMBEDDINGS_ENABLED` | **off** | On: the hybrid matcher. Off: the character matcher (today's production). | **Restart needed**: the matcher reads it when it is built at start-up |

Other switches that exist: `JIRA_ENABLED` (off stops Jira issues for tickets
**and** alerts; Teams alerts carry on), `SHADOW_MATCHER`,
`MESSENGER_PUBLIC_REPLIES`. All are read by `app/config.py` `flag()`.

**[CONFIRM]** who can edit `flags.json` on the VM out of hours. The PO and CC
lead need a login allowed to change that one file, or a named IT contact who
does it for them.

## 5. Setting up the Teams alerts (PO, once)

The alerts post into a Teams **group chat** through a Power Automate
"Workflows" webhook. Microsoft's screens change often: **[VERIFY]** each step
below against what Teams shows.

1. In Teams, create a group chat called **Chatbot alerts** with Dev, the PO
   and the CC lead **[CONFIRM members, e.g. Compliance]**.
2. In that chat, open **More options (…) > Workflows** (or the **Workflows**
   app) and choose the template **"Post to a chat when a webhook request is
   received"**.
3. Name it `Chatbot alerts`, sign in when asked, and pick the **Chatbot
   alerts** chat as where to post. Save.
4. Teams shows the webhook URL. Copy it. Anyone holding this URL can post into
   the chat, so treat it like a password.
5. Hand the URL to the deployer through the bank's approved secret-sharing
   route **[CONFIRM: e.g. the password manager]**. **Never** paste it in a
   chat, an email, a Jira issue or git.
6. The deployer adds it to `/etc/abz-chatbot/env`, in single quotes because it
   contains `&`:
   `ALERT_TEAMS_WEBHOOK_URL='https://...'`
   and runs `.venv/bin/python -m admin.alerts --test`. A "Test · chatbot alerts
   reach this chat" card should appear within a minute.
7. The flow runs under the account that created it. If that account is
   disabled, alerts stop without an error on our side. **[CONFIRM]** whether to
   create it under a shared or service account, and **[VERIFY]** that the
   bank's Microsoft 365 licences include this trigger.

To replace a leaked URL: delete the workflow, create it again (steps 2–6), and
restart nothing: the cron job reads the env file on every run.

**What the Workflow receives** (so the flow can be checked): a JSON body
`{"type": "message", "attachments": [{"contentType":
"application/vnd.microsoft.card.adaptive", "content": {Adaptive Card 1.4}}]}`.
The template posts each attachment's `content` as a card **[VERIFY the
template still reads `attachments`, and the highest card version it renders]**.

**Jira side.** Alerts use the same four `JIRA_*` settings as tickets; until
they are set, alert issues go to the mock log and show on
`/admin/jira-preview`. Set `ALERT_JIRA_PROJECT_KEY` to send alerts to a Dev or
IT project rather than the contact centre's queue **[CONFIRM the project with
the CC lead]**. The Jira account needs permission to create issues there, and
the project's priority scheme needs **Highest** and **High** **[VERIFY]**.
Add a Jira filter or notification on the label `chatbot-alert`.

## 6. The cron entry

The line is already in `deploy/crontab.example`; install that file as
`/etc/cron.d/abz-chatbot` (as root):

```cron
SHELL=/bin/bash
MAILTO=""
* * * * * root flock -n /tmp/abz-chatbot-alerts.lock /opt/abz-chatbot/current/deploy/admin.sh alerts >>/var/log/abz-chatbot/alerts.log 2>&1
```

- `deploy/admin.sh` reads `/etc/abz-chatbot/env` as root, then runs the
  script as the service user `abz`, so the env file stays **root-only, mode
  600**, and the files the script writes in `data/` stay writable by the app.
- It loads the same settings the service uses. Put every value in single
  quotes: bash and systemd both strip them **[VERIFY with the systemd version
  on the VM]**.
- `flock -n` skips a run if the previous one is still going (a slow Teams or
  Jira call).
- The script prints nothing unless a Teams or Jira send failed. Set `MAILTO`
  to the Dev inbox **[CONFIRM]** to get those lines by email, as a backstop.

Useful commands:

| Command | Does |
|---|---|
| `.venv/bin/python -m admin.alerts --dry-run` | Prints the cards and Jira issues it would send now. Sends nothing, changes no state. |
| `.venv/bin/python -m admin.alerts --test` | Posts one test card to Teams (or the mock file). |
| `cat data/alerts_state.json` | When each issue started and was last sent. Delete the file to reset the rate limits. |
| `tail data/alerts_mock.jsonl` | Cards written in mock mode (no Teams URL set). |

If `deploy/` (P7) uses systemd timers rather than cron, the same command as a
oneshot service with `EnvironmentFile=/etc/abz-chatbot/env`, `User=abz` and a
timer with `OnCalendar=minutely` does the same job without the quoting rule.

**Settings** (in `/etc/abz-chatbot/env`):

| Variable | Default | Read by |
|---|---|---|
| `ALERT_TEAMS_WEBHOOK_URL` | unset: mock mode | the cron job |
| `ALERT_HEALTH_URL` | `http://127.0.0.1:8000/health` | the cron job |
| `ALERT_ENV_NAME` | the VM's hostname | the cron job |
| `ALERT_JIRA_PROJECT_KEY` | `JIRA_PROJECT_KEY` | the cron job |
| `ALERT_TEAMS_REPEAT_MINUTES` / `ALERT_JIRA_REPEAT_HOURS` | 15 / 24 | the cron job |
| `ALERT_QUEUE_MAX_AGE_SECONDS` | 120 | the app (restart) |
| `ALERT_WEBHOOK_5XX_RATE` / `ALERT_SEND_FAILURE_RATE` | 0.01 / 0.02 | the app (restart) |
| `ALERT_WEBHOOK_REJECTED_MAX` | 2 | the app (restart) |
| `PURGE_HOUR` | 2 (02:00 Lusaka) | the app (restart) |

The thresholds are applied by the app, so `/health` and the alerts always
agree. The retention purges (audit log, sessions and the webhook inbox) run
when the app starts and every night at `PURGE_HOUR`, inside the app: no cron
entry is needed for them.

## 7. Meta webhook-failure emails

Meta emails the app's developers and admins when webhook deliveries to us keep
failing, and can switch the webhook subscription off after long failures
**[VERIFY current behaviour in Meta's webhook docs]**. Our own alerts cover
5xx and rejected signatures, but only Meta sees a request that never reaches
us (DNS, TLS, firewall).

- Make sure these emails go to the shared inbox **[CONFIRM address]**: the
  Meta app's contact email and the admins' notification settings.
- Dev checks that inbox every working morning. An email there is **Sev 2**:
  check `/health` (`webhook_errors`, `webhook_rejected`) and, in the Meta App
  Dashboard, that the webhook subscription for WhatsApp and the Page is still
  active; subscribe again if Meta switched it off.

## 8. On call

- **Business hours** (Monday to Friday 08:00–17:00 Lusaka **[CONFIRM]**): Dev
  owns every alert, acknowledges it in the chat, and fixes to the severity
  deadlines in §1.
- **Out of hours:** no developer on call. The PO and CC lead may **only** use
  the kill switches in §4, and post what they did in the chat. No code,
  content or other configuration changes. Dev picks up at the next working
  morning.
- A Sev 1 out of hours: kill switch within 15 minutes, then phone the PO (if
  the CC lead acted) and Compliance **[CONFIRM phone list]**.

## 9. Post-mortem template

Copy into a Jira comment or a page linked from the Sev 1 issue. Blameless:
describe what the system and the process allowed, not who slipped.

```markdown
# Post-mortem: <one-line title>  (Sev <n>, <DD/MM/YYYY>)

**Summary.** Two or three sentences: what customers saw, for how long, and
what we changed.

**Timeline (Lusaka time).**
- DD/MM/YYYY HH:MM  first sign (alert, customer, agent)
- HH:MM  acknowledged by
- HH:MM  contained (which kill switch)
- HH:MM  fixed and deployed (release tag)
- HH:MM  switched back on

**Impact.** Channels affected. Number of conversations or tickets (counts,
never customer details). Any fraud report or complaint delayed or lost, and
what was done for those customers.

**Cause.** What went wrong, and why our tests, evaluation gates or alerts did
not catch it first.

**What went well / what did not.**

**Actions.** Each with an owner and a date; add a test or a gate first.
| Action | Owner | Due |
|---|---|---|

**Compliance.** Was personal data involved? Was a notification needed, and
was it made? (Compliance fills this in.)
```
