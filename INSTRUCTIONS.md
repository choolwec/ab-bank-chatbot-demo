# Simple instructions — AB Bank chatbot (V1)

Plain-language guide for running and updating the chatbot. No programming
knowledge needed for most of this. (The technical version is `README.md`.)

---

## 1. Start the chatbot on your computer

Open **PowerShell**, then copy-paste these two lines:

```powershell
cd C:\Users\hp\Downloads\AB\ab-chatbot
.venv\Scripts\python -m uvicorn app.main:app --reload
```

Leave that window open — it IS the chatbot running.
Now open your browser and go to: **http://127.0.0.1:8000**

You'll see a demo page with a red **Chat** button at the bottom-right.
Click it and talk to the bot.

**First time on a new computer?** Run this once before the steps above:

```powershell
cd C:\Users\hp\Downloads\AB\ab-chatbot
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## 2. Things to try in the chat

- Click the buttons, or type freely
- "what is etumba" — normal question
- "wat is etumba" — misspellings still work
- "I lost my card" — emergency route fires immediately
- "I want to complain" — complaint intake with a reference number
- Type a made-up word twice — after two failures it offers a person
- Paste a fake 16-digit card number — the bot warns you and never stores it

## 3. Stop the chatbot

Go back to the PowerShell window and press **Ctrl + C** (or just close it).

## 4. Change what the bot says

The bot's answers live in text files here: `knowledge\intents\`
(accounts.yaml, etumba.yaml, loans.yaml, locations.yaml, fees.yaml,
smalltalk.yaml, urgent.yaml)

Everything else the bot says — the welcome, "I didn't quite catch that",
the questions it asks during a fraud report, complaint or callback, and the
"your reference is…" messages — is in one file:
`knowledge\system_messages.yaml`. Change the `text:` line; leave anything in
`{curly brackets}` as it is (the bot fills those in).

1. Open the file in any text editor (Notepad works, VS Code is nicer)
2. Find the answer, change the wording. To help the bot understand more
   ways of asking, add lines to the `phrases:` list
3. **Keep the spacing/indentation exactly as it is** — it matters
4. Check nothing broke (takes 3 seconds):

```powershell
cd C:\Users\hp\Downloads\AB\ab-chatbot
.venv\Scripts\python -m pytest -q
```

5. If it says all tests **passed**, save your change into the history book:

```powershell
git add -A
git commit -m "describe what you changed"
```

That git step is important — it's our audit trail of every wording change,
which is what we show a regulator or auditor.

### 4a. Other content files

- **`knowledge\templates.yaml`** — the WhatsApp messages staff can send
  after the customer's 24-hour window has closed. Meta must approve each one
  under the **same name**, and Legal must approve the wording. Keep them
  neutral (no offers, so Meta does not treat them as marketing), with **no
  links** and never asking for details. Leave `{{1}}` as it is: it is the
  case reference.
- **`knowledge\urgent_exemplars.yaml`** — example fraud and lost-card
  reports. A customer message that reads like one of these gets asked "is
  this a fraud report?" even if the keyword rules missed it. Add real
  reports the bot missed, in your own words. Never paste in sentences from
  the test sets under `tests\eval\`. After a change, a developer re-runs
  `python -m admin.calibrate_urgent`.
- **Out-of-scope phrases** (`out_of_scope` intent): short topical sentences
  about other services ("how do I reset my facebook password") and bare
  platform names work best.
- **Workshop and test phrasings:** phrases collected in the staff workshop
  or in the test sets are used to *measure* the bot. Never paste them into
  `phrases:` — you may reuse their words, not whole sentences. A test fails
  if a test sentence is copied into an intent.
- **Product answers must keep a way to a person:** every answer about
  accounts, loans, fees or eTumba keeps a "Request a callback" or "Talk to a
  person" button. A test (`tests\test_marketing.py`) checks this.

### 4b. Marketing consent, opt-out and feedback wording

All in `knowledge\system_messages.yaml`, all `status: draft` until Legal
signs them off:

- `lead.step.marketing_consent` — the optional last question in the
  callback request: may AB Bank send news and offers? The callback goes
  ahead either way. Also `lead.retry.marketing_consent`,
  `lead.summary.marketing_consent_yes` / `_no`, `field.marketing_consent`,
  and the buttons `button.yes_send_offers` / `button.no_thanks`.
- `marketing.opt_out` — the reply when a customer types "unsubscribe", "opt
  out", "stop offers" or "stop marketing".
- `csat.ask`, `csat.thanks`, `csat.thanks_down` and the buttons
  `button.csat_up` / `button.csat_down` — the short "how did we do?"
  question some customers get after a conversation is resolved.
- `desk.*` — notes that agents see in Chatwoot (not customers); the
  contact-centre lead reviews these.

Some entries have a `legal_note:` line. That is a question for Legal, not
text the customer sees; it appears as "For Legal:" in
`docs\intent-review.md`. Keep it when you edit the `text:`. The question
must never pre-assume a yes: a customer who is not asked is recorded as
"not asked", never as consenting.

To stop asking the consent question altogether, set
`"MARKETING_CONSENT_ENABLED": false` in `flags.json` (step 6).

## 5. Update branches, phone numbers, opening hours

- **Branches**: edit `knowledge\branches.json` — the entries in there now
  are placeholders and must be replaced with the real list
- **Phone numbers, emails, tariff-guide link**: edit the CONTACTS section
  near the top of `app\config.py` — anything that still says `[CONFIRM: …]`
  will show up literally in the chat until it's replaced
- Then run the tests and commit, same as step 4

## 6. Emergency off switches (no restart needed)

Open `flags.json` in the main folder:

- `"FREE_TEXT_ENABLED": false` → bot becomes buttons-only (typing is ignored)
- `"WIDGET_ENABLED": false` → chat disappears from the website entirely
- `"MARKETING_CONSENT_ENABLED": false` → the callback flow stops asking about news and offers
- `"WA_LINK_ENABLED": true` → shows "Continue on WhatsApp" in the chat (keep it
  `false` until the official WhatsApp number is confirmed)

Save the file — it takes effect immediately. Set back to `true` to restore.

**Write `true` or `false` exactly, with no quotation marks.** `"false"` in
quotes is ignored and the switch stays **on**. The full list of switches,
and how to use them during an incident, is in `docs\runbook-incidents.md`
section 4. On the live server, a setting in the server's environment file
overrides `flags.json`, so ask the developer if a change seems to have no
effect.

## 7. Weekly report (for the improvement loop)

```powershell
cd C:\Users\hp\Downloads\AB\ab-chatbot
.venv\Scripts\python -m admin.report --days 7
```

This **writes the report to `data\report.md`** (open it in any text
editor or VS Code); it no longer prints it in the window. Add `--stdout` to
print it instead, or `--out somewhere.md` to save it elsewhere.

It shows conversations per channel, the launch targets (PASS / FAIL, or
n/a when there is not enough data yet), tickets, the "how did we do?"
answers, leads and campaigns (counts only, no names or numbers), and the
**top unmatched questions** — add those as new `phrases:` in the intent
files each week (step 4).

The report is a draft: a qualified person must check the figures before
they go into any management or board report. The WhatsApp cost line uses
illustrative rates, in US dollars, that still need checking against Meta's
price list.

## 8. The document for legal

`docs\intent-review.md` contains every bot answer plus a checklist of every
unconfirmed fact. After any content change, refresh it with:

```powershell
.venv\Scripts\python -m admin.legal_export
```

Nothing goes live until legal signs off every answer in that document.

## 9. Putting it on the internet, and connecting Jira

Right now the bot only runs on your own computer (step 1) — fine for demos,
but real website visitors need it running somewhere that's always on, and
the contact-center handoff is still in mock mode. Both of those are
one-time setup jobs, not day-to-day tasks, so they get their own document:
**`docs/deployment-and-jira-setup.md`** (also available as a PDF in the
same folder to hand to whoever ends up owning either piece).

## 10. If something breaks

1. Run the tests (step 4, line 4) — the error message names the file and
   line that's wrong; usually it's spacing in a `.yaml` file you just edited
2. Undo your last change if stuck: `git checkout -- knowledge\`
   (this restores the knowledge files to the last committed version)
3. Still stuck? The bot window (PowerShell from step 1) shows errors in red
   — read the last few lines
