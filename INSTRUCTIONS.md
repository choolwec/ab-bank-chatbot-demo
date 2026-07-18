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

Save the file — it takes effect immediately. Set back to `true` to restore.

## 7. Weekly report (for the improvement loop)

```powershell
cd C:\Users\hp\Downloads\AB\ab-chatbot
.venv\Scripts\python -m admin.report --days 7
```

Shows sessions, fallback rate, tickets, and the **top unmatched questions**
— add those as new `phrases:` in the intent files each week (step 4).
Add `--out report.md` to save it as a file instead.

## 8. The document for legal

`docs\intent-review.md` contains every bot answer plus a checklist of every
unconfirmed fact. After any content change, refresh it with:

```powershell
.venv\Scripts\python -m admin.legal_export
```

Nothing goes live until legal signs off every answer in that document.

## 9. If something breaks

1. Run the tests (step 4, line 4) — the error message names the file and
   line that's wrong; usually it's spacing in a `.yaml` file you just edited
2. Undo your last change if stuck: `git checkout -- knowledge\`
   (this restores the knowledge files to the last committed version)
3. Still stuck? The bot window (PowerShell from step 1) shows errors in red
   — read the last few lines
