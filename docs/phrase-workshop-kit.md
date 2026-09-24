# Phrase workshop kit (tickets N1 and N8)

> **Draft for the content owner and product owner to review.** Written
> 24/09/2026. The workshop is planned for W04 (19–23/10/2026) in
> `execution-plan.md` §12.

## Summary

A 2-hour workshop where contact-centre and social-media staff write down
how customers **actually** ask things: Zambian English, abbreviations,
typos, and Bemba or Nyanja mixed with English. The phrasings become the
**golden evaluation set** that measures the assistant (N1), and at least
100 code-mixed phrases, checked by native speakers, feed the code-mixed
evaluation (N8).

**Targets:** at least **15 phrasings per intent** from the workshop (53
intents, so about 800), rising to 30 per intent with the staff trial; at
least **100 code-mixed** phrasings in total, each checked by a Bemba or
Nyanja speaker.

**What we don't collect:** names, phone numbers, account or card numbers,
NRCs, or anything copied from a real customer's message that could identify
them. Paraphrase instead. The capture sheet records a **role**, never a
name.

## 1. Before the workshop

| Task | Owner | When |
|---|---|---|
| Book a room (or Teams call) for 2 hours; invite 10–20 staff from the contact centre and social team, including Bemba and Nyanja speakers | CO | W03 |
| Print this kit's §4 (the intent list), one copy per table | CO | W03 |
| Make one copy of `docs/phrase-capture-template.csv` per group (a shared spreadsheet is easiest) | CO | W03 |
| Pick two **reviewers** for labelling (§6) and two native-speaker **checkers** (one Bemba, one Nyanja) for §7 | PO | W03 |
| Have the website bot on staging open on a screen for the demo | Dev | Day |

## 2. Agenda (2 hours)

| Time | Item | Who |
|---|---|---|
| 0:00–0:10 | Why we're here: the bot understands only phrasings like the ones it has seen; today we write down how customers really talk. Rule: no real customer details | PO |
| 0:10–0:20 | Demo on staging: a question it gets right, a misspelling it gets right, a code-mixed one it misses | Dev |
| 0:20–0:30 | How to write phrasings (§3), with five examples done together | CO |
| 0:30–1:15 | **Round 1, by topic.** Groups of 3–4, each with a block of intents from §4 (accounts; eTumba and fees; loans; branches and contact; urgent and small talk). At least 15 phrasings per intent, into the sheet | Groups |
| 1:15–1:25 | Break; groups swap sheets and add phrasings the other group missed | Groups |
| 1:25–1:45 | **Round 2, code-mixed.** Bemba and Nyanja speakers lead; everyone contributes what they hear from customers. Include greetings, "money", "card", "my account", thanks | Native speakers |
| 1:45–1:55 | **Round 3, out of scope.** Things customers ask that the bank's bot shouldn't answer (other banks, mobile-money providers, government services, general chat). Use intent `out_of_scope` | Everyone |
| 1:55–2:00 | Thanks; what happens next (§6); how staff can keep adding during the staff trial | PO |

## 3. How to write phrasings

Write each phrasing **the way a customer would type it on a phone**, not
the way the bank would write it.

- **One question per row.** "How do I open an account" and "what do I need
  to open an account" are two rows (and two intents).
- **Keep typos and short forms.** "hw do i opn acc", "pls", "wat", "u",
  "ur", "acc", "bal", "thx", "kwacha", "K500".
- **Zambian English.** "I want to know about…", "How much is the charges",
  "Where can I find your branch at Kabwe", "My money has not reflected".
- **Vary the length.** A single word ("statement"), a short question, and a
  long story ("I went to the agent yesterday and sent money but it did not
  go through…").
- **Different starting points.** Questions, statements, complaints,
  greetings mixed in ("hi, how do i register etumba").
- **Code-mixed.** Write what you actually hear customers type, mixing
  Bemba or Nyanja with English. The native speakers in the room give the
  examples; this kit deliberately contains none, because it wasn't written
  by a native speaker. Set the `language` column (below). Don't translate
  English phrasings word for word; write what customers say. A native
  speaker checks every one afterwards (§7).
- **No personal data.** Made-up amounts and places are fine; names,
  numbers and anything from a real conversation are not.
- **Don't look at the bot's existing phrases**, and don't test your phrasing
  on the bot first. We want fresh wording.

**Capture sheet columns** (`docs/phrase-capture-template.csv`):

| Column | What to write |
|---|---|
| `intent` | The intent id from §4, exactly as written (for example `etumba_register`), or `out_of_scope` |
| `phrasing` | The customer's words |
| `language` | `en` (English, including Zambian English), `bem-en` (Bemba mixed with English), `ny-en` (Nyanja mixed with English), `bem` or `ny` (no English), or `other-en` (another Zambian language mixed with English: tell the CO which one) |
| `contributor_role` | `contact_centre`, `social_media`, `branch` or `other`. **No names** |

The examples in this section are illustrations for the workshop only:
they are not in the evaluation data and must not be added to it.

## 4. Per-intent capture sheet

Every intent the assistant has today, generated from
`knowledge/intents/*.yaml` (53 intents). Tick off each intent as the group
reaches 15 phrasings, and note how many are code-mixed.

| # | Area | Intent id | What it covers | Phrasings (≥ 15) | Code-mixed |
|---|---|---|---|---|---|
| 1 | Accounts | `account_types_overview` | Types of accounts | | |
| 2 | Accounts | `savings_account` | Savings account | | |
| 3 | Accounts | `current_account` | Current account (Tamanga) | | |
| 4 | Accounts | `tamanga_plus_account` | Tamanga Plus (premium current account) | | |
| 5 | Accounts | `business_account` | Business account (Mukula Plus) | | |
| 6 | Accounts | `business_account_requirements` | Business account documents by entity type | | |
| 7 | Accounts | `savings_plan_account` | Savings Plan account | | |
| 8 | Accounts | `kids_savings_account` | Kids Savings account | | |
| 9 | Accounts | `term_deposit_account` | Term Deposit Account (TDA) | | |
| 10 | Accounts | `joint_account` | Joint accounts | | |
| 11 | Accounts | `foreign_national_account` | Account opening for foreign nationals | | |
| 12 | Accounts | `account_opening_requirements` | What you need to open an account | | |
| 13 | Accounts | `account_opening_how` | How to open an account | | |
| 14 | Accounts | `bank_statement_request` | Getting a bank statement | | |
| 15 | Accounts | `account_reactivation` | Reactivating a dormant account | | |
| 16 | Accounts | `sort_swift_code` | Sort code / SWIFT code | | |
| 17 | eTumba | `etumba_what_is` | What is eTumba? | | |
| 18 | eTumba | `etumba_register` | Register for eTumba | | |
| 19 | eTumba | `etumba_ussd` | Using *888# | | |
| 20 | eTumba | `etumba_fees` | eTumba fees | | |
| 21 | eTumba | `etumba_cash_in_out` | eTumba cash in / cash out | | |
| 22 | eTumba | `etumba_pull_push_funds` | Move money between eTumba and my bank account | | |
| 23 | eTumba | `etumba_transfer_mobile_money` | Transfer between eTumba and Airtel/MTN/Zamtel | | |
| 24 | eTumba | `yaka_savings` | Yaka savings | | |
| 25 | eTumba | `zesco_token` | Retrieving a ZESCO token | | |
| 26 | eTumba | `etumba_reversal` | Reverse a wrongly sent eTumba transfer | | |
| 27 | eTumba | `etumba_balance_check` | Check eTumba balance | | |
| 28 | Fees | `fees_tamanga` | Tamanga fees | | |
| 29 | Fees | `fees_charges` | Fees & charges | | |
| 30 | Loans | `msme_loan` | Business (MSME) loans | | |
| 31 | Loans | `agri_loan` | Loans for farming businesses | | |
| 32 | Loans | `personal_loan` | Personal loans (government employees) | | |
| 33 | Loans | `sme_overdraft` | SME overdraft | | |
| 34 | Loans | `loan_requirements` | Loan requirements | | |
| 35 | Loans | `guarantor_definition` | What is a guarantor? | | |
| 36 | Loans | `collateral_definition` | What counts as collateral? | | |
| 37 | Loans | `loan_apply_how` | How to apply for a loan | | |
| 38 | Branches and contact | `branch_locator` | Find a branch (starts the locator flow) | | |
| 39 | Branches and contact | `agent_locator` | Find an eTumba agent (starts the locator flow) | | |
| 40 | Branches and contact | `opening_hours` | Opening hours | | |
| 41 | Branches and contact | `contact_details` | Contact details | | |
| 42 | Out of scope | `out_of_scope` | Something else | | |
| 43 | Small talk and handoff | `greeting` | Say hello | | |
| 44 | Small talk and handoff | `thanks_goodbye` | Thanks / goodbye | | |
| 45 | Small talk and handoff | `bot_capabilities` | What can you do? | | |
| 46 | Small talk and handoff | `about_ab_bank` | About AB Bank | | |
| 47 | Small talk and handoff | `human_handoff` | Talk to a person (starts the lead flow) | | |
| 48 | Technical | `technical_issue` | App or online banking not working | | |
| 49 | Urgent | `fraud_scam` | Report fraud or a scam (starts the fraud flow) | | |
| 50 | Urgent | `lost_stolen_card` | Lost or stolen card (starts the fraud flow) | | |
| 51 | Urgent | `complaint` | Make a complaint (starts the complaint flow) | | |
| 52 | Urgent | `emergency_line` | Emergency number | | |
| 53 | Urgent | `credential_trouble` | Forgot PIN or password | | |

If an intent is added or renamed before the workshop, regenerate this list
from `knowledge/intents/*.yaml` (the `intent` and `label` fields).

## 5. After the workshop: the Dev's preparation

1. Collect the groups' sheets into one CSV with the four template columns.
   Remove exact duplicates and any row that contains personal data (the CO
   checks by eye).
2. Build the **labelling file**: a new CSV with the columns
   `text,predicted_intent,score,action,label_a,label_b`, the same layout
   `python -m admin.export_utterances` writes. Put each phrasing in `text`;
   leave the other columns empty. **Don't copy the contributor's `intent`
   into the file**: the reviewers label blind, and the contributor's intent
   is kept aside as a cross-check.
3. Save it as `data/workshop_utterances.csv` (the `data/` folder is never
   committed).

## 6. Two-person labelling

The same procedure is used for workshop phrasings, for the weekly staff-trial
export, and later for "bot got this wrong" messages (H4).

1. **Weekly export during the staff trial:**
   `python -m admin.export_utterances --days 7` writes masked customer
   messages to `data/utterances.csv`. It drops anything that still looks
   personal (a second check after masking) and button taps.
2. **Reviewer A** fills `label_a` for every row, alone. **Reviewer B** fills
   `label_b` on a separate copy, alone. Each label is an intent id from §4,
   or `oos` for out of scope. Don't discuss rows while labelling.
3. The Dev merges the two copies into one file with both columns filled.
4. **Import:** `python -m admin.import_labels data/utterances.csv` (or the
   workshop file). Rows where both reviewers agree go into
   `tests/eval/golden.yaml`; unknown intent names are rejected;
   **disagreements are printed**.
5. The **PO settles each disagreement** (picks a label or drops the row),
   and the Dev re-imports the settled rows. The golden file is merged, never
   overwritten.
6. For workshop rows, the Dev also lists rows where the agreed label differs
   from the contributor's intent. They usually point to a confusing intent
   boundary: send them to the CO.
7. Commit `tests/eval/golden.yaml` with the full suite green.

**Rules that keep the measurement honest:**

- Golden phrasings are **test data**. Never copy a golden, held-out or
  code-mixed evaluation phrasing into an intent's `phrases:` (a test
  enforces this for the held-out set). The CO may use the **vocabulary**
  (words and spellings customers use) in new, different phrases through
  normal content work.
- When `golden.yaml` has at least 30 phrasings per intent, the Dev adds
  golden gates to both gate files at their measured values and re-runs
  `python -m admin.calibrate` (`remaining-work-plan.md` §3 N1).

## 7. Code-mixed collection (N8)

- **Target: at least 100** code-mixed phrasings (`bem-en`, `ny-en`, `bem`,
  `ny`), spread across intents, with the urgent intents (`fraud_scam`,
  `lost_stolen_card`, `complaint`) and the common ones (balance, eTumba,
  branches, thanks) well covered.
- **Every one is checked by a native speaker** of that language: is it
  natural, and does it mean what the intent says? The checker marks each
  row OK, fixed (with the corrected text), or dropped. Record the checker's
  role, not their name.
- The Dev replaces the unverified seed in `tests/eval/code_mixed.yaml`
  with the checked phrasings (keeping `lang` per item), removes
  `seed_unverified`, and runs `python -m admin.eval_code_mixed`. A model
  change is decided only on these checked phrasings (`remaining-work-plan.md`
  §3 N8).
- Code-mixed phrasings also go through two-person labelling (§6) if they
  are to join the golden set.

## 8. Checklist

| # | Step | Owner | Done when |
|---|---|---|---|
| 1 | Workshop held | CO | Sheets collected |
| 2 | Sheets merged, PII removed | Dev + CO | `data/workshop_utterances.csv` exists |
| 3 | Two reviewers labelled blind | Reviewers | Both columns filled |
| 4 | Imported; disagreements settled | Dev + PO | `golden.yaml` committed, suite green |
| 5 | ≥ 100 code-mixed phrasings checked by native speakers | CO + checkers | Checked list handed to the Dev |
| 6 | `code_mixed.yaml` replaced; `eval_code_mixed` run | Dev | Results in the status note |
| 7 | ≥ 30 per intent (with the staff trial); golden gates added | Dev | Gates committed |
