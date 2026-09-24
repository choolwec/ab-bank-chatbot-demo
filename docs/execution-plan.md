# Execution plan: building the AB Bank assistant, week by week

**Tickets, specs, schedule, people, launch and operations**

Written 2026-09-23 · Covers W01 (Mon 28 Sep 2026) to W22 (Fri 26 Feb 2027) · Status: proposed.

> **What this is.** [`excellence-plan.md`](excellence-plan.md) says *what*
> excellent means and *why*. This document says **who does what, in which
> order, and how we'll know each piece is done**.
>
> The background lives in the other research docs:
> - [`multi-platform-research.md`](multi-platform-research.md): channels, law
>   and cost
> - [`conversational-research.md`](conversational-research.md): the 15-case
>   probe and the repair patterns
> - [`../research/matcher-benchmark/`](../research/matcher-benchmark/): the
>   measured matcher results
>
> **How to use it:**
> - Every ticket has an ID (`S1`, `C6`, `W2`…). Branches, pull requests, commit
>   messages and the weekly status note all refer to that ID.
> - Appendix A is the full index. Update its **Status** column in the same pull
>   request that finishes a ticket, so the plan stays the source of truth.
> - Dates are targets. **Phases are gated by exit criteria, not by the
>   calendar.** If a gate isn't met, the next phase waits.

---

## 1. The plan on one page

**Milestones**

| Milestone | Target | What's true when we hit it |
|---|---|---|
| **M0: Safe baseline** | Fri 9 Oct 2026 (end W02) | Both safety gaps are fixed. CI runs on every push. The evaluation harness and baseline metrics exist. |
| **M1: Conversational** | Fri 6 Nov 2026 (end W06) | All 15 probe cases pass. The new system messages are legally approved. |
| **M2: Understands** | Fri 4 Dec 2026 (end W10) | The local embedding model meets the §1 understanding and safety targets on the evaluation sets, after two weeks in shadow mode. The Lusaka production server is up. |
| **M3: Website live (soft)** | Week of 7 Dec 2026 (W11) | Public website launch with no marketing, *if* the go/no-go passes. Otherwise it moves to W16, after the holiday freeze. |
| **M4: WhatsApp pilot** | Staff from Mon 4 Jan 2027 (W15). Limited public from W17. | The official number runs on the bot, with the handoff and templates working. |
| **M5: Messenger live** | W18 (week of 25 Jan 2027) | Meta App Review has passed and the Page Inbox handoff is tested. |
| **M6: Full launch** | W22 (22–26 Feb 2027) | The agent desk is live, every §1 target is met across all three channels, and launch communications have gone out. |

**The critical path isn't code.** Three things decide the WhatsApp date:

1. **The legal ruling** on Data Protection Act s.70/71, plus the privacy notice.
   It must be done by **W14**.
2. **A Zambian production server.** It must be provisioned by **W08**.
3. **Meta Business verification and the WhatsApp number.** These must be done
   by **W12**.

All three start in **W01**. If the legal ruling slips, WhatsApp slips with it,
but the website launch doesn't depend on it.

**Effort.** About **100 developer-days** of engineering (Appendix A). One
full-time developer fills the 22 weeks with very little slack. **Adding a second
developer or contractor from W06** for the platform and channel work (P, W, M
tickets) buys a 3–4 week buffer. Content, legal and contact-centre work runs in
parallel with its own owners (§2).

---

## 2. People and responsibilities

| Role | Who (to confirm) | Time needed | Owns |
|---|---|---|---|
| **Product owner (PO)** | Project lead | ~1 day/week | Priorities, go/no-go calls, this plan, the weekly status |
| **Developer (Dev)** | Project lead with Claude Code, or a contractor | Full-time | S, E, C, N, P, W, M and H tickets |
| **Second developer** (recommended from W06) | Contractor | Full-time, W06–W20 | P, W, M and H tickets |
| **Content owner (CO)** | Marketing or product person | ~2 days/week | All customer-facing wording, `short_label`, `answer_simple`, the tone guide, `[CONFIRM` resolution |
| **Legal / DPO** | Legal team | ~0.5 day/week, more in W01–W10 | L1–L8, and signing off every content release |
| **Compliance / IT risk** | Compliance / CISO | Checkpoints | Bank of Zambia cyber guidelines, hosting approval, the DPIA |
| **Contact-centre lead (CC)** | Contact centre | ~0.5 day/week | Handoff process, SLAs, agent training, Jira/Chatwoot use |
| **Social-media team (SM)** | Social team | Workshops, then the pilot | Phrase collection, Messenger/WhatsApp operations today, Page Inbox |
| **Operations / Risk** | Ops | Decisions | The 24/7 fraud route and out-of-hours promises |
| **Sponsor** | Management | Monthly | Budget, unblocking, bank-owned Meta assets |

**Who does what.** R = responsible, A = accountable, C = consulted.

| Area | R | A | C |
|---|---|---|---|
| Engineering tickets | Dev | PO | CO |
| Content releases | CO | PO | Legal |
| Legal rulings | Legal | Sponsor | PO, Compliance |
| Meta onboarding | PO | Sponsor | Marketing |
| Hosting | PO + Dev | Sponsor | Compliance / IT risk |
| Handoff operations | CC | PO | SM |

---

## 3. Working agreements

- **Branches.** Use one branch per ticket: `feat/<ID>-<slug>` (e.g.
  `feat/S1-urgent-scan`). Pull requests go to `master`. **Never** commit
  straight to `master`.
- **Definition of Ready.** Before work starts, a ticket needs its acceptance
  criteria, any content wording drafted by the CO (or marked TBD), and all its
  dependencies merged.
- **Definition of Done:**
  1. Code and tests are written, and the **full suite passes locally and in CI**.
  2. The `CLAUDE.md` invariants still hold (masking first, the button guarantee,
     fraud/complaint tickets never closed by the bot, `PROXY_HOPS`).
  3. The evaluation gates (E3) haven't regressed.
  4. Any new customer-facing text lives in YAML with `status: draft` and appears
     in the legal export.
  5. `CLAUDE.md` or `README.md` is updated if the architecture changed.
  6. The change has been demonstrated on staging.
  7. The ticket's Status is updated in Appendix A.
- **Content pull requests** can't be merged into a *production release* until
  Legal signs off the regenerated `docs/intent-review.md`.
- **Release rhythm:**
  - Every merge to `master` deploys to **staging**, which holds synthetic data
    only.
  - **Production** releases happen fortnightly on Thursdays, after the legal
    sign-off of that release's content.
  - **Safety hotfixes** (S tickets, or any fraud-routing bug) can go out the same
    day, with a PO and Dev review.
- **Environments:**

  | Environment | Where | Data | Purpose |
  |---|---|---|---|
  | Development | A developer's laptop | Synthetic | Building and testing |
  | Staging | Render (the current `render.yaml`) | **Synthetic only.** Staff are told not to use real personal data. | Demos, staff trial, Meta test number |
  | Production | An always-on VM in a Lusaka data centre (P7) | Real, masked | Customers |

- **Weekly status note** (PO, every Friday): tickets finished, gate status,
  blockers, and any decisions needed. Keep it to half a page.

### Running tickets with Claude Code

Use one session per ticket, on its own branch. This prompt keeps sessions
consistent:

> Implement ticket **<ID>** from `docs/execution-plan.md`. Read `CLAUDE.md` first
> and preserve every invariant listed there. Work on branch
> `feat/<ID>-<slug>`. Write the tests listed under the ticket's **Tests** and
> **Acceptance** before or alongside the code. Put all new customer-facing
> wording in YAML with `status: draft`, not in Python. Run the full test suite
> and the evaluation gates, and paste the results. Update the ticket's Status in
> Appendix A. Then open a pull request describing what changed and what a
> reviewer should try on staging.

**Reviewer checklist** (for the PO or second developer):

- Does the diff match the ticket?
- Were any tests deleted or loosened? That's never allowed.
- Is any new text hardcoded in Python?
- Do the invariants still hold?
- Try the staging steps from the pull request yourself.

---

## 4. Phase 0: safe baseline (W01–W02 → M0)

### S1 · Urgent detection: catch real fraud and stop false alarms

**Why.** These were measured on the current `guards.urgent_scan()`.

- **Misses** (returns `None`):
  - "someone stole money from my etumba"
  - "they stole my money"
  - "someone took money from my account"
  - "my money was taken without my permission"

  The first only reached the fraud flow because the fuzzy matcher happened to
  pick the lost-*card* intent, so the customer was told to secure a card.
- **False alarms:**
  - "I didn't make it to the branch today, what time do you open tomorrow" and
    "I did not make the deadline for my loan documents" both open the **fraud
    flow**. The cause is the bare substring "did not make" in `FRAUD_PHRASES`.
  - "I don't want to complain, just a question" and "is it rude to ask about
    fees" both open a **complaint**.

**Change** (`app/guards.py`, `app/flows/fraud.py`, `knowledge/system_messages.yaml`
once C1 exists):

1. **Split the signals into two kinds.**
   - **Hard signals** go straight into the flow, as today: *stolen, stole,
     steal, scam, fraud, hacked, phishing, unauthorised, someone took, taken
     from my account, withdrew without, lost/stolen card*, plus common
     misspellings.
   - **Soft signals** get a *confirmation question* instead:
     - "did not make", but only when it's followed by transaction, payment,
       withdrawal or transfer
     - money gone / missing / disappeared
     - complain / complaint / rude / unacceptable
   - The confirmation for money looks like: "It sounds like something may be
     wrong with your money. Do you want to report it as fraud? [Yes, report it]
     [No, I have a question]".
2. **Handle negation.** "Don't want to complain", "not a complaint", "no
   problem" and "not stolen" suppress the soft signals. Negation *never*
   suppresses a hard signal.
3. **Choose the fraud intro by what was taken.** A card gets the card-block
   intro. Money, eTumba or the account gets the money-theft intro.
   `lost_stolen_card` should only use the card wording when the message
   actually mentions a card.
4. Keep urgent detection **before** the active flow, as today. The order in
   `router._route()` doesn't change.

**Tests:**

- A new `tests/test_urgent.py`, parametrised over `tests/data/urgent_positive.txt`
  (≥ 60 lines: tense variants, Zambian English, misspellings, eTumba/card/account
  variants) and `tests/data/urgent_negative.txt` (≥ 30 lines, including every
  false alarm above).
- Positive lines must return a hard signal, or a soft signal whose confirmation
  leads into the fraud flow. Negative lines must return `None`.

**Acceptance:**

- 100% of the positive lines are routed.
- 0 of the negative lines open a flow without confirmation.
- Existing flow tests still pass.

**Size:** M (2 days) · **Depends on:** — · **Owner:** Dev. Ops/Risk reviews the
confirmation wording.

### S2 · The fraud flow collects contact details

**Why.** `FraudFlow.steps` asks for `what_happened`, `when` and `channel`, and
never for a way to reach the customer. Yet `finish()` promises "a member of
staff will contact you as a priority". On the web there's no identity at all, so
staff can't follow up. The complaint flow already asks.

**Change** (`app/flows/fraud.py`):

- Add a `contact` step: "What's the best phone number to reach you on?"
- Validate it with the existing `is_valid_zambian_phone`, and also accept an
  email address.
- Allow "skip", but then state the consequence plainly: "Without a number we
  can't call you back. Please call {contact_phone}."
- Read the value back ("Got it: 0977 123 456").
- The Jira description already lists every field, so nothing changes there.
- Later, W3 prefills this on WhatsApp when the number is known, and asks the
  customer to confirm it.

**Tests:** extend `test_fraud_urgent_fires_mid_conversation_with_transcript`.
The ticket row must contain `contact`, and a phone number entered twice must be
read back.

**Acceptance:** every fraud ticket created through the flow has a `contact`
field, either a value or an explicit `skipped`.

**Size:** S (1 day) · **Depends on:** — · **Owner:** Dev. CO writes the wording.

### S3 · A red-team suite that checks where messages end up

**Why.** `tests/test_redteam.py` only checks "no crash, no dead end, no card
digits echoed". It doesn't check where a message was *routed*.

**Change:** add `tests/data/redteam.yaml` with entries of the form
`{text, expect: {action|intent|flow|not_flow}}`. It covers the existing 16
lines, S1's positive and negative cases, PII lines (checking the masked form
reaches the audit log), and prompt-injection-style lines (which must get the
normal fallback, never an echo). Keep the old test file.

**Acceptance:** the suite runs in CI (E1). Any routing change that breaks an
entry fails the build.

**Size:** S (1 day) · **Depends on:** S1

### E1 · Continuous integration

**Change:** add `.github/workflows/ci.yml`. On every push and pull request it
runs Python 3.11 on Ubuntu, `pip install -r requirements.txt`, `pytest -q`, and
`python research/matcher-benchmark/bench_matcher.py` (informational). Protect
`master` so a pull request needs green CI.

**Acceptance:** a failing test blocks a merge. A badge in `README.md` shows the
status.

**Size:** S (0.5 day) · **Owner:** Dev. PO sets up branch protection in GitHub.

### E2 · A framework for conversation tests, plus the 15 probe cases

**Change:** add `tests/conversations/*.yaml` and a runner, `tests/test_conversations.py`.
Each file is one multi-turn script:

```yaml
id: probe-06-typed-cancel
fixes: C2                       # the ticket that should make this pass
xfail: true                     # remove when C2 lands (strict: an unexpected pass fails the build)
turns:
  - payload: human_handoff
  - say: cancel
    expect:
      action: cancel            # meta["action"]
      active_flow: null
      flow_data_lacks: {name: cancel}
      strikes: 0
      last_buttons_include: [menu]
```

The runner drives `router.handle()` directly with a fresh `SessionStore` and a
temporary data directory, which is fast and never touches `data/`. It supports
these `expect` keys:

- `action`, `intent`, `active_flow`
- `flow_data_has` / `flow_data_lacks`
- `strikes`
- `text_contains` / `text_lacks`
- `last_buttons_include`
- `ticket_created` (a type)
- `replies_max` (the bubble count)

Encode all 15 probe cases from `conversational-research.md` §3. The 3 that pass
today are plain tests. The other 12 are `xfail(strict=True)`, tagged with the
ticket that fixes each one.

**Acceptance:** `pytest` reports 3 passes and 12 expected failures. Each C
ticket turns its cases into real passes.

**Size:** M (2 days) · **Depends on:** —

### E3 · Evaluation gates for understanding and out-of-scope

**Change:**

- Move `research/matcher-benchmark/heldout_v0.py` into `tests/eval/heldout.yaml`
  (in-scope `{text, intent}` and out-of-scope `{text}`).
- Add `tests/test_eval_gates.py`. At the production thresholds it computes:
  - the rate of correct direct answers
  - the rate of **wrong** direct answers
  - the rate of **out-of-scope questions answered directly**
  - the "did you mean…?" coverage
- Compare those against `tests/eval/gates.yaml`. It starts **at today's
  baseline** (e.g. `oos_direct_max: 0.267`, `wrong_direct_max: 0.044`,
  `right_direct_min: 0.538`).
- The **ratchet rule:** when a ticket improves a metric, the same pull request
  tightens the gate. Gates are never loosened without a written reason in the
  pull request.
- Add `python -m admin.eval_report` to print the same numbers, with the failing
  items listed.

**Acceptance:** the gates fail if, for example, a content edit makes a hard
lookalike like "how do i open a facebook account" start getting a direct answer.

**Size:** S (1 day) · **Depends on:** —

### E4 · Record the baseline

**Change:** add `docs/metrics-baseline.md`, generated once: E3's numbers, E2's
pass count, bubble counts per path, red-team results, and the date and commit.
This is the "before" picture every later claim is measured against.

**Size:** S (0.5 day) · **Depends on:** E2, E3

### P8 · Protect the admin routes

**Why.** `GET /admin/jira-preview` has no authentication. That has to change
before any staff trial carries names or phone numbers, even on staging.

**Change:** add HTTP Basic auth driven by the `ADMIN_USER`/`ADMIN_PASSWORD`
environment variables, compared in constant time. If they aren't set, the route
returns 404, so it's off by default. This applies to every `/admin/*` route,
current and future.

**Tests:** 401 without credentials, 200 with them, and 404 when not configured.

**Size:** S (0.5 day)

**M0 exit (end W02):**

- S1–S3, E1–E4 and P8 are merged.
- CI is green, with 12 expected failures and no unexpected ones.
- The baseline is committed.
- The §10 decisions from `excellence-plan.md` have owners.

---

## 5. Phase 1: conversational (W02–W06 → M1)

The designs here follow `conversational-research.md` §4. This section adds the
file-level detail.

### C1 · Move system messages into YAML

**Change:**

- Add `knowledge/system_messages.yaml`, keyed by name, e.g. `welcome`,
  `fallback`, `two_strike`, `abuse`, `resume`, `resume_flow`, `pii_warning`,
  every flow prompt, retry and finish text, and the new C-ticket texts. Each
  entry has `text:` and `status: draft|approved`.
- Add `app/messages.py` with `msg(key, **fmt)`, which raises a `KeyError` at
  start-up for any missing key.
- `router.py`, `guards.py` and `flows/*.py` replace their string constants with
  `msg()` calls.
- `admin/legal_export.py` gets a "System messages" section, and its `[CONFIRM`
  scan covers them.

**Tests:**

- Every `msg()` key referenced in the code exists. Use a grep-based test over
  `app/`.
- The legal export contains every key.
- The existing wording tests (e.g. "automated", "not a person") still pass.

**Acceptance:** no customer-facing English is left in `app/*.py`, apart from
button labels, which move with C11 and P3.

**Size:** M (2 days) · **Depends on:** — · **Owner:** Dev. CO copies the wording
in.

### C2 · Typed commands that work anywhere

**Change** (`app/router.py`):

- After the urgent scan and **before** the active flow, normalise the text
  (lowercase, strip punctuation, collapse whitespace). If the *whole message* is
  in the command table, dispatch it as the matching payload:

  | Typed | Payload |
  |---|---|
  | cancel, stop, never mind, nevermind, quit | `cancel_flow` |
  | menu, main menu, start again, restart, 0 | `menu` |
  | agent, human, person, talk to a person, speak to someone, customer care | `human_handoff` |
  | repeat, say again, say that again | `repeat` (C4) |
  | help | `menu` + capability text |

- **Whole-message only.** "Cancel my card" stays a lost-card report.
- In an active **fraud or complaint** flow, `cancel_flow` asks for confirmation
  first ("Your report isn't sent yet. Stop anyway? [Yes, stop] [No, continue]"),
  stored as `flow_state["confirm_cancel"]`.

**Tests:** make probe cases 6 and 7 pass. Add cases for "cancel my card" (still
fraud), "stop" mid-fraud (asks for confirmation), and "0" on the menu.

**Size:** S (1.5 days) · **Depends on:** E2, C1

### C3 · Understanding answers to the bot's own questions (yes/no, numbers, typed labels)

**Change:**

- Add `session.expecting` to `app/session.py`.
- After `router.handle()` has built its final replies, store the options from
  the last reply's buttons: `[(label, payload), …]`. Store a `yes` and a `no`
  payload when the reply declares them, using new keys on the reply dict, set by
  the flow or intent. For example, "anything else?" maps yes → `menu` and no →
  `thanks_goodbye`.
- In `_route()`, after commands and before the active flow and matcher, match
  the input against `expecting`:
  - a digit or number word from 1 to 9 picks that option;
  - a yes-word (yes, yeah, yes please, ok, sure, ehe) or a no-word (no, no
    thanks, that's all) picks the declared payload;
  - text that fuzzy-matches an option label at ≥ 90 picks that option.
- Clear `expecting` on any unmatched input, so a stale "yes" can't fire later.
- The **web widget** already shows buttons. This mainly matters for WhatsApp and
  for people who type.

**Tests:** probe cases 10 and 14. Also: a "2" after the menu opens the second
item, and a "yes" after an answer that asked no question falls through to the
matcher.

**Size:** M (2 days) · **Depends on:** E2

### C4 · Let customers repair the bot's turn

**Change:**

- Add `session.last_replies`: the last bot replies, already masked and rendered.
- Typed "repeat" (from C2) resends them.
- "What do you mean", "I don't understand", "explain" and "huh" send the last
  intent's **`answer_simple`**, a new optional YAML field that's plainer and
  legally approved. If there isn't one, repeat the last message with a "Talk to
  a person" button.
- **Neither case counts as a strike.**

**Tests:** probe case 9, plus a case for an intent with `answer_simple` and one
without.

**Size:** S (1.5 days) · **Depends on:** C1, C2 · **Content:** CO writes
`answer_simple` for the 15 most-used intents (K1).

### C5 · Recognise frustration

**Change:**

- Add `guards.is_frustrated()`: a phrase list ("not helping", "you don't
  understand", "I already told you", "waste of time", "useless bot"), messages
  containing "!!!", and all-caps messages of three or more words.
- Route it after the abuse check, with its own `frustration` message: calm, an
  apology, and a human offer.
- It never counts as a strike. Log it as `action=frustration`.

**Tests:** probe case 13, plus negatives such as "is it helpful to open a
savings account?".

**Size:** S (1 day) · **Depends on:** C1

### C6 · Classify every in-flow message: digressions and corrections

**Change** (`app/router.py`, `app/flows/base.py`):

**Digressions** are handled in the router *before* `flow.handle()`. A message
counts as one when all three of these hold:

1. It's question-shaped: it ends with "?" or starts with a question word
   (what, when, where, how, why, can, do, does, is, are, which).
2. The matcher's top intent is **not** a flow intent, with a score of at least
   `HIGH_CONFIDENCE` (tighter for fraud/complaint: `+0.05`).
3. For validator steps: the input also *fails* the validator.

Then the bot sends the intent's answer, and on the **same** reply appends
`msg("back_to_flow", flow=<label>)` plus the current prompt from
`flow.resume()`. `flow_state` is untouched, and it's never a strike.

**Corrections** are handled in `FormFlow`:

- Add an optional `correctable` flag on each step, and use the existing
  validators.
- If the input contains a correction marker (sorry, actually, I meant, wrong,
  correction, "not X but") **and** a substring that passes an *earlier* step's
  validator:
  1. Update that field.
  2. Reply with `msg("corrected", field=<label>, value=<read-back>)`.
  3. Re-ask the *current* step.

**Tests:** probe cases 3, 4 and 5. Also:

- A free-text fraud answer containing "when" ("they took money when I was at the
  ATM") is stored as the answer, *not* treated as a digression.
- A correction of the phone number during the time step works.

**Acceptance:** those cases pass, and no fraud report ever ends because of a
digression.

**Size:** L (4 days) · **Depends on:** C1, C3

### C7 · Confirm before sending, and read values back

**Change:**

- The lead and complaint flows get a final `confirm` step. It summarises what
  will be sent ("Mary Banda · 0977 123 456 · a loan · morning") with **[Send it]
  [Change something]**.
- "Change something" shows one button per field. The chosen field is re-asked,
  then the summary comes back.
- Phone numbers are always read back formatted as `0977 123 456` (a helper in
  `flows/base.py`).
- The fraud flow **doesn't** get a confirmation step, to stay fast. Its finish
  message shows the summary instead.

**Tests:** the confirm path, the change path, and read-back formatting.

**Size:** M (2.5 days) · **Depends on:** C1

### C8 · Pre-fill the fraud flow from the first message

**Change:**

- Add `app/extract.py`:
  - `when`: a keyword list (today, this morning, last night, yesterday,
    weekdays, "N days ago"), then `dateparser` (BSD-3, **add to
    requirements.txt**) with `PREFER_DATES_FROM=past` and `DATE_ORDER=DMY`. The
    result is stored as `when_hint`, and **the raw text is kept**.
  - `channel`: keywords (etumba, card, atm, online/internet banking, myabz,
    branch names from `branches.json`).
  - `amount`: a `K\s?\d+` or `ZMW\s?\d+` pattern.
- When the fraud flow starts from a free-text trigger of at least 5 words:
  1. Set `what_happened` to the trigger text.
  2. Fill `when` and `channel` from the extraction.
  3. Ask **one** confirmation question ("You said this happened **yesterday**,
     involving **eTumba**. Is that right? [Yes] [No, let me explain]") instead
     of three questions.
  4. If the answer is "No", fall back to the normal steps.

**Tests:**

- Probe case 2.
- Fixed-date tests using `RELATIVE_BASE`: "10am" must **never** become a date,
  which was a measured dateparser misread.
- A short trigger ("scam") still asks every step.

**Size:** M (3 days) · **Depends on:** S2, C6

### C9 · Carry context between questions

**Change:**

- Add an optional `follow_ups:` map to intents, e.g. `current_account:
  {fees: fees_tamanga, requirements: account_opening_requirements}`.
- A small resolver runs when the message is short (8 words or fewer) and either
  contains a pronoun (it, that, this, one) or is a generic question (how much,
  what do I need, where). If the matcher's top result is a generic sibling of
  the current topic's follow-up target, it switches to the follow-up.
- Log `context_boost` in the audit metadata.

**Tests:** probe case 1, plus a case showing context expires after two turns or
a topic change.

**Size:** M (2 days) · **Depends on:** — · **Content:** CO fills in `follow_ups`
for the account, eTumba and loan topics.

### C10 · Two questions in one message

**Change:**

- Split on " and ", " also " and "?" into at most two clauses, each of at least
  3 words.
- If both clauses match at or above `HIGH_CONFIDENCE`, answer both in **one**
  reply, joined by `msg("and_also")`, using the union of their buttons (at most
  5).
- Otherwise, keep today's behaviour.

**Tests:** probe case 8. "I want to open an account and get a loan" answers
both. "Stolen and blocked card" isn't split, because it's urgent and handled
first.

**Size:** S (1.5 days) · **Depends on:** C1

### C11 · Warmth without touching the facts

**Change:**

- Acknowledgement variants (`ack` list in YAML) rotate by `len(transcript) %
  n`. That keeps it **deterministic**, so tests stay stable.
- Once the customer has given their name, use it once per conversation
  ("Thanks, Mary").
- The medium-confidence fallback names the category: "I can see this is about
  **loans**. Which of these is closest?".
- Button labels move to YAML (`short_label`, K1).

**Tests:** rotation is deterministic, the name is used exactly once, and the
category appears in the fallback text.

**Size:** S (2 days) · **Depends on:** C1, K1

### K1 · Content: short labels, simple answers, voice and tone *(content owner, W02–W06)*

- **`short_label`** (20 characters or fewer) for every label that's too long:
  **37 of the 81** today. Add a test asserting it exists wherever `len(label) >
  20`.
- **`answer_simple`** for the 15 most-used intents.
- **`docs/voice-and-tone.md`:** plain English (aim for a primary-school reading
  level), 3 short paragraphs at most, one question per message, the key fact
  first, never blaming, fixed words for key terms (eTumba, MyABZ, `*888#`), and
  how to write apologies.
- Legal reviews in two batches, W04 and W06.

### K2 · Resolve the `[CONFIRM` placeholders *(business owners, W01–W10)*

There are **17 customer-facing placeholders**:

| Where | Count | Owner |
|---|---|---|
| `branches.json` (phones, sort codes, the branch-count discrepancy) | 9 | Operations |
| `app/config.py` (24-h emergency line, tariff URL) | 2 | Ops / Marketing |
| `urgent.yaml` (reset route) | 2 | Operations |
| `technical.yaml` (status page) | 1 | IT |
| `locations.yaml` (Saturday hours conflict) | 1 | Contact centre |
| `locator.py` (finding a nearby agent) | 1 | eTumba team |
| `complaint.py` (response-time commitment, from the BoZ Directive) | 1 | Compliance |

Track them in the weekly status. **Every one must be resolved before M3.**

**M1 exit (end W06):**

- All 15 probe cases pass, and no `xfail` is left in `tests/conversations/`.
- The system messages and K1 batch 1 are legally approved.
- The E3 gates haven't regressed.
- Bot messages per scripted fraud report are 4 or fewer (measured by E2's
  `replies_max`).

---

## 6. Phase 2: understanding (W04–W10 → M2)

### N1 · A golden evaluation set from real sources

The engineering part (1.5 days):

- `admin/export_utterances.py` exports **masked** user messages from the audit
  log, meaning staging staff-trial traffic from W03 and later production data,
  to CSV with columns `text, predicted_intent, score, action`. It de-duplicates
  and removes anything that still looks like PII, as a second check after
  `guards.mask()`.
- `admin/import_labels.py` turns a reviewed CSV back into
  `tests/eval/golden.yaml`.

The data part:

- **Staff phrase workshop, W04, 2 hours,** with the social-media and
  contact-centre teams. For each intent: "how do customers actually say this?"
  Collect Zambian English, abbreviations and code-mixed phrasings. The target is
  at least 15 per intent.
- **BANKING77 mapping:** download the dataset manually (CC BY 4.0, and credit it
  in `tests/eval/README.md`), then map the overlapping intents to ours:
  card lost or stolen, transfer problems, top-ups, fees, PIN, and so on.
- **The target is at least 30 phrasings per intent**, with every label checked
  by two people. Disagreements go to the PO.

**Size:** M (1.5 days dev plus the workshop plus the CO's labelling time) ·
**Depends on:** E3, the staging staff trial (§11)

### N2 · An out-of-scope set of at least 300

Include:

- generic off-topic questions
- **hard lookalikes**, in the style of `heldout_v0` (government services, other
  companies' products, telecoms, utilities)
- the CLINC150 out-of-scope queries, **if** their licence allows it; confirm
  first, and use only our own items if not
- every real out-of-scope message from the staff trial

Stored in `tests/eval/oos.yaml`. **Size:** S (1 day plus data)

### N3 · A local embedding model in the matcher

**Change:**

- Add `app/embedder.py`. It loads `models/all-MiniLM-L6-v2/onnx/model.onnx` and
  its `tokenizer.json` with **onnxruntime** (MIT) and **tokenizers** (both added
  to `requirements.txt`), and does mean pooling with L2 normalisation.
- The model files are **not in git**. They're downloaded once from the
  **official source**, `sentence-transformers/all-MiniLM-L6-v2` (Apache-2.0),
  by `admin/fetch_model.py`, which **verifies the sha256** pinned in
  `config.EMBED_MODEL_SHA256`. A wrong hash means the app refuses to use the
  model and logs an error.
- `Matcher` pre-computes phrase embeddings at load time, and `match()` returns
  both scores.
- Ranking uses the hybrid `0.5·char + 0.5·emb`. The **decision** (answer,
  "did you mean", or fallback) uses the embedding score against new thresholds,
  `EMB_HIGH` and `EMB_MEDIUM`, set by N5.
- Add a kill switch, `EMBEDDINGS_ENABLED`, following the `flags.json`/env
  pattern. When it's off, or the model is missing, the bot falls back to exactly
  today's behaviour.
- Update the architecture notes in `CLAUDE.md`.

**Tests:**

- All existing matcher tests pass in **both** modes.
- `test_all_phrases_reach_their_intent` runs with embeddings on.
- The E3 gates run in both modes.
- Model start-up takes under 3 s, and p95 match time is under 20 ms (measured
  in CI and logged).

**Size:** L (4 days) · **Depends on:** E3, N1 (a first cut is enough)

### N4 · Shadow mode

**Change:**

- With `SHADOW_MATCHER=true`, production keeps answering with the *current*
  decision logic, while also computing the embedding decision and logging it as
  `action=shadow` with both predictions.
- `python -m admin.shadow_report --days 7` lists the disagreements, grouped by
  intent, for weekly review.

**Acceptance:** two consecutive weekly reviews show the new decision is right on
at least 80% of disagreements, and never worse on out-of-scope questions.

**Size:** M (2 days) · **Depends on:** N3

### N5 · Threshold calibration

**Change:**

- `python -m admin.calibrate` splits golden and out-of-scope into
  calibration/test sets (fixed seed). It chooses `EMB_HIGH` to hold
  out-of-scope direct answers at **3% or less** on the calibration split, and
  reports test-split metrics against the §1 targets.
- Optionally, it adds a split-conformal bound on the wrong-answer rate.
- Its output is a patch to `app/config.py` plus a pull request note. **Never
  tune on the test split.**

**Size:** S (1.5 days) · **Depends on:** N1, N2, N3

### N6 · An explicit out-of-scope intent

**Change:**

- Add an `out_of_scope` intent in `knowledge/intents/out_of_scope.yaml`, whose
  `phrases:` are the hard-lookalike patterns, with an approved answer: "That's
  not something I can help with here. I can help with accounts, eTumba, loans
  and branches, or connect you to our team." Include buttons.
- The E3 gate counts a match to `out_of_scope` as a *correct* abstention.

**Size:** S (1.5 days) · **Depends on:** N2 · **Content:** CO

### N7 · A second, model-based urgent check

**Change:**

- Embed around 60 fraud exemplars from S1's positive set.
- If a message's similarity to them reaches `EMB_URGENT` (calibrated on S1's
  positive and negative sets), route it the way a *soft* signal is routed (with
  a confirmation question), even if the rules missed it.
- Either check can trigger the fraud path. Neither can suppress the other.

**Acceptance:** red-team fraud recall stays at 100%, and the negative set
triggers at most 2% confirmations.

**Size:** S (1.5 days) · **Depends on:** N3, S1

### N8 · Code-mixed phrases

**Change:**

- Collect at least 100 code-mixed Bemba/Nyanja–English phrases from the N1
  workshop and the staff trial.
- Evaluate the current model against a multilingual MiniLM/E5-small (check each
  licence).
- Switch only if code-mixed accuracy improves without breaking the E3 gates.

**Size:** S (1 day plus data)

**M2 exit (end W10):**

- On the **golden and out-of-scope test splits**: direct answers are right at
  least 85% of the time and wrong at most 2% of the time, and out-of-scope
  direct answers are at most 3%.
- Red-team fraud recall is 100%.
- Two shadow reviews have been done.
- Legal has approved Tier 2 models (L7).
- The production VM is up (P7).

---

## 7. Phase 3a: channel-ready core (W07–W12, second developer)

These follow `multi-platform-research.md` §7.

### P1 · A persistent session store

**Change** (`app/session.py`):

- `SqliteSessionStore`, backed by `data/sessions.db`, with the table
  `sessions(key TEXT PRIMARY KEY, channel TEXT, created REAL, last_active REAL,
  state TEXT)`. `state` is the JSON of the `Session` dataclass, and its
  transcript is already masked.
- The key is `f"{channel}:{user_key}"`, and the web uses its session ID as the
  user key.
- Separate the two timeouts:
  - `IDLE_REGREET_MINUTES = 30` greets the customer again but **keeps** any
    flow.
  - `FLOW_EXPIRY_HOURS = 24`, or **72 for the fraud and complaint flows**,
    expires the flow.
- Purge sessions on the same schedule as `TRANSCRIPT_RETENTION_DAYS`.
- Keep `SessionStore` (in memory) for tests.
- The "one process" rule stays, because SQLite writes are serialised with a
  lock. Update the `CLAUDE.md` session section.

**Tests:** survives a restart (write, reload the store, read), expiry rules,
concurrent-write safety, and purging.

**Size:** M (3 days)

### P2 · A channel interface

**Change:**

- `app/channels/base.py` defines `InboundMessage(channel, user_key, text,
  payload, location, media_type, msg_id, ts)` and a `Channel` protocol.
- `app/channels/web.py` takes over the `/chat` logic from `main.py` **with no
  behaviour change**. All existing tests must pass untouched.

**Size:** M (2 days) · **Depends on:** P1

### P3 · A per-channel renderer, with limit tests

**Change:**

- Add `app/render.py`, pure functions following the rules in
  `multi-platform-research.md` §7.3:
  - 1–3 buttons become WhatsApp reply buttons.
  - 4–10 become a list message, with `short_label` as the row title and the full
    label as the description.
  - Messenger gets up to 13 quick replies.
  - Body-length rules apply per channel.
- **The human option is never dropped**, and `button.id` is self-describing
  (`loc_city:Lusaka`).
- Add `tests/test_render_limits.py`: for **every intent**, for every channel,
  render its reply and assert the platform limits.

**Acceptance:** a content edit that breaks a WhatsApp limit fails CI, just as a
dead end does today.

**Size:** L (4 days) · **Depends on:** P2, K1

### P4 · Per-channel kill switches and per-user rate limits

**Change:**

- Add `WHATSAPP_ENABLED` and `MESSENGER_ENABLED`. When one is off, the bot sends
  one static approved reply (888 and opening hours) and hands off to a human.
- Keep the per-IP limiter on `/chat` only.
- Add a **per-user** limiter for webhooks, because every webhook arrives from
  Meta's IP addresses.

**Size:** S (1.5 days) · **Depends on:** P2

### P5 · Fewer message bubbles

**Change:**

- Add a `merge_replies` option in `router.handle()`. It joins consecutive bot
  replies (the PII warning, flow intros) into one message, keeping only the last
  reply's buttons.
- It's on for WhatsApp and Messenger. The web keeps separate bubbles unless the
  CO prefers merged ones.

**Tests:** `replies_max` in E2 for WhatsApp mode.

**Size:** S (1 day)

### P6 · Audit: channel column and hashed identities

**Change:**

- Add a `channel` column to `events` and `tickets`, with a migration that
  defaults existing rows to `web`.
- `user_hash = HMAC-SHA256(USER_KEY_SECRET, key)[:32]`. **The raw phone number
  or Messenger ID is never logged.**
- Tickets gain `channel` and a minimised `reply_to`.

**Tests:** the migration runs on a copy of today's schema, no raw ID appears
anywhere in `events`, and the HMAC is stable.

**Size:** M (2 days) · **Depends on:** P1

### P7 · Production hosting in Lusaka

**Provision** (with PO and Compliance):

- An always-on VM (2 vCPU, 4 GB RAM, 40 GB SSD is ample), running Ubuntu LTS.
- **Tier III, ISO 27001** data centres to get quotes from: Paratus Lusaka,
  Infratel, MTN.

**Engineering (3 days):**

- `deploy/` holds a systemd unit (a **single** uvicorn worker), an nginx
  reverse proxy with a Let's Encrypt or bank certificate, and `PROXY_HOPS=1`.
- Environment variables are set through a root-only `.env`, never in git.
- Nightly `sqlite3 .backup` of `audit.db` and `sessions.db`, kept for 14 days,
  with an off-VM copy inside Zambia.
- logrotate.
- An external uptime check on `/health`.
- A `deploy.sh` that does a git pull of the **release tag**, `pip install`, runs
  the tests, then restarts.

**Runbook:** `docs/runbook-production.md` covers deploying, rolling back to the
previous tag, restoring a backup, and rotating secrets.

**Acceptance:**

- A deploy and a rollback have each been done twice.
- A backup has been restored successfully.
- `/health` is green from outside the network.

**Depends on:** hosting procurement (§10), which must be ready by W08.

### P9 · Load and soak test

**Change:** `research/load/` has a Locust or plain `httpx` script that sends 20
messages/s for 30 minutes to staging, then to production before M3. Record the
p95 latency and memory use. The target is p95 of 150 ms or less server-side,
with no memory growth.

**Size:** S (1 day) · **Depends on:** P1, P7

---

## 8. Phase 3b: WhatsApp (W11–W17 → M4)

### W1 · Meta onboarding *(PO, non-engineering, W01–W12)*

| Week | Step | Done when |
|---|---|---|
| W01 | Confirm or create a **bank-owned** Meta Business portfolio with at least 2 bank admins | Admins are named in the status note |
| W01–W04 | **Business verification** (company documents) | Verified badge shows in Business Settings |
| W03 | Create the Meta app, add the WhatsApp and Messenger products, and create a **System User** with a non-expiring token | Token stored in the password manager |
| W04 | **Number decision**: migrate 0769651262, use coexistence, or a new number (`multi-platform-research.md` §5.1) | Decision recorded |
| W06 | Dev works against Meta's **test number** (staging) | W2–W4 testable |
| W10 | Register the production number, get the **display name** approved, set the **2FA PIN**, add a **payment method** | Number shows "Connected" |
| W11 | Submit the **utility templates** (W7). Apply for the **Official Business Account** (blue badge). | Templates approved |

### W2 · The webhook endpoint

**Change:**

- `app/channels/whatsapp.py` handles:
  - `GET /webhooks/whatsapp`: the verify-token handshake, using a constant-time
    compare.
  - `POST /webhooks/whatsapp`: verify `X-Hub-Signature-256` over the **raw
    body**; reject with 401 if it fails. Then `INSERT OR IGNORE` each message
    into the `inbound` table (`wamid` as the primary key, which gives
    de-duplication for free), and **return 200 immediately**.
- A single asyncio worker is started in `lifespan`. It processes unprocessed
  rows in arrival order, one user at a time.

**Tests:** recorded payloads in `tests/data/wa/*.json` covering a good and a bad
signature, a duplicate delivery (processed once), a burst from one user (kept in
order), and a worker crash (the row is picked up again after restart).

**Size:** M (3 days) · **Depends on:** P2, P6

### W3 · Parsing incoming messages

**Change:**

- Parse text, `interactive.button_reply` and `interactive.list_reply` (mapped
  to a payload), location, media types (image, document, audio, video, sticker),
  and `statuses` (for delivery metrics).
- `user_key` is the BSUID `user_id`, falling back to `wa_id`.
- The phone number, where present, goes only to the S2 contact prefill (for the
  customer to confirm) and is never logged raw.

**Size:** M (2 days) · **Depends on:** W2

### W4 · Sending messages

**Change:**

- Send text, reply buttons, lists and location requests.
- On each inbound message, mark it read and show the typing indicator.
- Retry 429 and 5xx responses with exponential backoff (at most 5 attempts),
  and write permanent failures to the audit log.
- Use the thin `httpx` client that's already a dependency.

**Tests:** request bodies checked against recorded examples, and retry
behaviour with a mocked transport.

**Size:** M (3 days) · **Depends on:** P3, W3

### W5 · Media and voice notes

**Change:**

- **Nothing is downloaded or stored.**
- Images and documents get `msg("media_not_accepted")`. It explains the
  customer's safety (cards and NRCs), invites them to describe the problem in
  words, and includes buttons.
- Audio gets `msg("voice_not_supported")`.
- Log the media type only.

**Size:** S (1 day)

### W6 · A location-based branch finder

**Change:**

- The CO and Operations add `lat`/`lng` to every branch in `branches.json`.
- The locator offers a WhatsApp location request. The reply is matched to the
  nearest branches by haversine distance (top 3, with distances).

**Size:** S (1.5 days) · **Depends on:** W4

### W7 · Utility templates

- Three templates: `case_received`, `case_update` and `callback_scheduled`. The
  wording is approved by Legal (L6), neutral, with no links, and always quotes
  the reference number.
- Staff send `case_update` for tickets older than 24 h through `/admin/…`
  (behind P8's auth) until H2 exists.

**Size:** S (1 day) · **Depends on:** W4, L6

### W8 · The 24-hour window and stale messages

**Change:**

- Track `last_inbound_at` per user. The sender **refuses** free-form replies
  outside the 24-h window and suggests a template instead.
- Inbound messages more than 10 minutes old (because of Meta retries after an
  outage) get `msg("sorry_delay")` plus the menu, and are **never** used to
  silently resume a flow.

**Size:** S (1.5 days) · **Depends on:** W2, P1

### W9 · WhatsApp-specific content

Add `answer_by_channel` to intents. The first use is `contact_details`, which
shouldn't say "WhatsApp us on…" to someone already on WhatsApp. **Size:** S (0.5
day)

### W10 · Pilot runbook *(PO + CC)*

1. **Staff pilot, W15–W16:** around 30 staff, two weeks, a daily defect
   triage.
2. **Limited public pilot, W17 onwards:** the number is announced only through
   a branch QR code and the website "Continue on WhatsApp" link, with no mass
   marketing.
3. **Go/no-go criteria for each stage:** §1 targets met on the pilot data, no
   severity-1 incidents in the last 7 days, and handoff SLA of at least 95%.

**M4:** staff pilot starts W15, and the public pilot starts W17 if the gate
passes.

---

## 9. Phase 3c: Messenger (W15–W18 → M5)

### M1 · The App Review pack

- A privacy-policy URL on abbank.co.zm, covering chatbot data, retention and
  the Meta processor role. Legal writes it.
- A **screencast script** showing the consent context, a real message exchange
  and the handoff.
- A reviewer test user.
- Submit at the **end of W15**, and budget for one resubmission.

**Size:** S (1 day plus Legal) · **Depends on:** M2 (a working bot on a test
Page)

### M2 · The Messenger adapter

**Change:**

- `app/channels/messenger.py`: webhook (verify, signature), parsing text,
  quick-reply payloads, postbacks and echoes, then quick-reply rendering through
  P3.
- The PSID is the `user_key`, hashed in the audit log.

**Size:** M (3 days) · **Depends on:** P2, P3

### M3 · The Page profile

Set up through the Graph API, from a script under `admin/`, so the
configuration lives in git:

- the Get Started button
- the greeting text (disclosure plus scope)
- a persistent menu mirroring `MENU_BUTTONS`, with "Talk to a person" always
  in it
- 3–4 ice breakers

**Size:** S (1 day)

### M4 · Handover to the Page Inbox

**Change:**

- On "Talk to a person", create the ticket, then `pass_thread_control` to the
  Page Inbox. Subscribe to `messaging_handovers` and standby.
- When a message echo comes from an app other than ours (a human replied), set
  `bot_paused_until`.
- Control comes back when the agent marks the conversation Done, or after 24 h.

**Tests:** recorded webhook sequences.

**Size:** M (2.5 days) · **Depends on:** M2, H1 · **Note:** confirm the current
conversation-routing setup screens in Business Suite.

### M5 · Private replies to urgent public comments

**Change:**

- Subscribe to the Page `feed`.
- For comments where S1 or N7 detects urgency, send **one** private reply (text
  only, within 7 days) with the fraud or complaint entry point.
- A public reply is posted **only** from comms-approved wording, and only when
  the PO enables it.

**Size:** M (2 days) · **Depends on:** M2, S1 · **Owner:** SM approves.

---

## 10. Non-engineering tracks (start in W01)

| ID | Track | Owner | Start → due | Blocks |
|---|---|---|---|---|
| L1 | **DPIA** for all three channels and Tier 2 models | DPO | W01 → W06 | M3 |
| L2 | **Legal ruling on s.70/71** (Meta processing outside Zambia): the lawful basis, whether an ODPC authorisation or approved contract is needed, and asking peer banks how they handled it | Legal | W01 → **W10 (hard stop W14)** | **M4 (critical path)** |
| L3 | **Privacy notice and first-contact consent wording** for web, WhatsApp and Messenger | Legal + CO | W03 → W06 | M3, M4 |
| L4 | **Bank of Zambia cyber and IT-risk engagement:** hosting, third parties (Meta, the DC), and whether notification is needed | Compliance | W02 → W10 | M3 |
| L5 | **Retention periods** for transcripts, tickets, sessions and evaluation sets (replaces today's placeholders) | Legal | W02 → W06 | P1, M3 |
| L6 | **Utility template wording** (W7) | Legal | W08 → W10 | W7 |
| L7 | **Approval of local, non-generative models** (Tier 2) | Legal / DPO | W05 → W08 | N3 in production |
| L8 | **ODPC registration check:** does it cover chatbot processing and list the processors? | DPO | W01 → W04 | M3 |
| H-P | **Hosting procurement:** request quotes from Paratus, Infratel and MTN (W01), choose (W04), contract (W05), VM delivered (**W08**) | PO + Sponsor | W01 → W08 | **P7 → M2, M3, M4** |
| O1 | **Operations decisions:** the 24/7 fraud route and out-of-hours promise, handoff hours and SLA, the handoff tool | Ops + CC | W01 → W03 | S2 wording, H3 |
| O2 | **Holiday change-freeze window** (confirm the bank's policy; assumed mid-Dec to early Jan) | PO | W02 | Schedule |
| MK1 | **Launch communications:** publish the official WhatsApp number everywhere, anti-scam messaging, branch QR codes | Marketing | W12 → W22 | M4, M6 |

---

## 11. Phase 4: humans and operations (W15–W22 → M6)

### Staff trial of the website (from W03, on staging)

Around 20 staff use the website bot on staging with synthetic data only (names
like "Test Customer", no real numbers). This builds the golden set (N1) and
finds bugs early. Reset staging data weekly.

### H1 · Tickets that carry the channel and a reply address

- Every ticket records its `channel`, the `reply_to` (hashed ID plus an
  encrypted contact reference), and whether the 24-h window is open.
- The Jira description shows the channel and how to reply ("reply within 24 h
  via inbox; after that, use template `case_update`").

**Size:** S (1 day) · **Depends on:** P6

### H2 · A unified agent desk (Chatwoot, self-hosted in Lusaka)

**Change:**

- Deploy Chatwoot on a second VM in the same data centre. Check the licence of
  the edition you choose **[VERIFY]**.
- Create an **API-channel** inbox.
- **On handoff:** create or look up the contact (hashed ID, plus a name if one
  was given), create the conversation, post the masked transcript as a private
  note, and set the status to *open*.
- **Agent replies** arrive through the Chatwoot `message_created` webhook and
  are sent through our channel adapter. The adapter enforces the 24-h rule and
  prompts for a template if the window has closed.
- **When the conversation is resolved,** the bot is unpaused.
- Jira stays the system of record for fraud and complaint tickets, and Chatwoot
  links to the Jira key.

**Tests:** the whole round trip with a mocked Chatwoot, and pause/resume.

**Size:** XL (6 days) · **Depends on:** H1, W4, M2 · **Owner:** CC trains the
agents in W19.

### H3 · Opening hours and out-of-hours promises

Contact-centre hours move into config. Out of hours, handoff and complaint
confirmations promise the next working day, and **fraud always shows the
emergency route decided in O1**.

**Size:** S (1 day) · **Depends on:** O1

### H4 · A "bot got this wrong" loop

Agents tag a conversation `bot-wrong` in Chatwoot, or add a Jira label. A weekly
export adds the tagged messages to the N1 labelling queue.

**Size:** S (1.5 days) · **Depends on:** H2, N1

### H5 · Sampled one-tap CSAT

After around 20% of *resolved* conversations (sampled; on WhatsApp every message
costs money), ask one question with 👍 / 👎 buttons. Report the results by
channel.

**Size:** S (1.5 days)

### H6 · Weekly quality report, version 2

**Change:** `admin/report.py` gains:

- per-channel breakdowns
- every §1 metric compared with its target (✅/❌)
- strikes per conversation, repairs, corrections, digressions resumed, re-asks
- delivery failures, cost per conversation, and CSAT

Its output is `data/report.md`, plus a copy attached to the weekly status note.

**Size:** M (2 days) · **Depends on:** P6, the new actions from C2–C11

### R1 · Runbooks and alerts *(done before the W15 staff pilot)*

`docs/runbook-incidents.md` defines severity levels and first steps:

| Severity | Examples | First response |
|---|---|---|
| **Sev 1** | A fraud report not routed; PII in logs; a wrong fee quoted | Kill switch (`FREE_TEXT_ENABLED=false` or channel off) within 15 minutes, notify PO and Compliance, fix, write a post-mortem |
| **Sev 2** | Channel outage; webhook failures; Meta quality rating drops | Fix within 1 working day |
| **Sev 3** | A wrong-but-safe answer | Next content release |

- **Alerts:** `/health` down, webhook 5xx above 1%, send failures above 2%, the
  worker queue older than 2 minutes, and Meta webhook-failure emails going to a
  shared inbox.
- **On call:** Dev during business hours. Out of hours, only kill switches
  (documented for the PO and CC lead).

**Size:** M (2 days)

### R2 · Go/no-go checklists *(PO)*

Each checklist is a markdown table filled in and signed in the pull request that
tags the release.

- **M3 (website):**
  - every `[CONFIRM` is resolved and all content is legally approved
  - P7 is done
  - L1, L3, L4 and L8 are done
  - R1 exists
  - the §1 safety targets are met
- **M4 (WhatsApp):** everything in M3, plus L2, W1 complete, W2–W8 done, the
  templates approved, and the staff pilot's go/no-go passed.
- **M5 (Messenger):** App Review passed, and M4 (the Page Inbox handoff) tested
  with the social team.
- **M6 (full launch):** H2 live and agents trained, all §1 targets met on 2
  weeks of real traffic, and MK1 ready.

**M6 exit:** every §1 target is met on every channel for two consecutive weeks,
and the weekly quality rhythm is running.

---

## 12. Week-by-week schedule

"Eng" lists the tickets being worked on, with the second developer's work in
*italics*. ◆ marks a milestone.

| Week | Dates | Eng | Content / legal / ops | Meta / hosting | Launch |
|---|---|---|---|---|---|
| W01 | 28 Sep–2 Oct | **S1, S2, E1**, S3 | Kickoff. O1 decisions. L1, L2 and L8 start. K2 starts. | Meta portfolio check. Hosting quotes requested. | — |
| W02 | 5–9 Oct | E2, E3, E4, P8, C1 | Tone guide draft. L4 and L5 start. O2 confirmed. | Business verification submitted | ◆ **M0** |
| W03 | 12–16 Oct | C2, C3, C4 | K1 batch 1 (short labels). L3 draft. | Meta app and System User created | Staff trial on staging starts |
| W04 | 19–23 Oct | C5, C6 | **Staff phrase workshop (N1).** Legal review of K1 batch 1. | Hosting chosen. Number decision. | — |
| W05 | 26–30 Oct | C6 (cont.), C7 | K1 batch 2 (`answer_simple`). L7 starts. | Hosting contract | — |
| W06 | 2–6 Nov | C8, C11 · *C9, C10* | Legal review of system messages and K1 batch 2 | Test number working on staging | ◆ **M1** |
| W07 | 9–13 Nov | N1 tools, N2, N3 · *P1* | Golden-set labelling | — | — |
| W08 | 16–20 Nov | N3 (cont.), N4, N6 · *P6* | L6 (templates) starts. L7 decision. | **VM delivered** | Shadow mode on staging |
| W09 | 23–27 Nov | N5, N7, N8 · *P7* | L2 ruling expected | — | — |
| W10 | 30 Nov–4 Dec | P9, M3 go/no-go preparation · *P7 done, P2, P3* | Every `[CONFIRM` resolved. **L2 due.** | Production number registered, display name, payment method | ◆ **M2**. M3 go/no-go on Friday. |
| W11 | 7–11 Dec | *P3 (cont.), P4, P5* · W2 | Content release 1 approved | Templates submitted. Blue-badge application. | ◆ **M3 website soft launch** (if go) |
| W12 | 14–18 Dec | W3, W4 · *W8, W9* | MK1 planning | — | Website monitoring |
| W13 | 21–25 Dec (holiday) | W5, W6 (reduced week) | — | — | Change freeze (to confirm) |
| W14 | 28 Dec–1 Jan (holiday) | W7, R1 (reduced week) | L2 **hard stop** | — | Change freeze (to confirm) |
| W15 | 4–8 Jan | M2, M3, M1 · *H1* | Agent pilot briefing | Messenger App Review submitted (end of week) | ◆ **M4 WhatsApp staff pilot** |
| W16 | 11–15 Jan | Pilot fixes · *H3* | — | Waiting for App Review | Staff pilot, week 2. Website launch here if moved from W11. |
| W17 | 18–22 Jan | M5, H5 · *H2* | MK1: QR codes and website link | — | **WhatsApp limited public pilot** (if go) |
| W18 | 25–29 Jan | M4 · *H2* | — | App Review result | ◆ **M5 Messenger live** (if approved) |
| W19 | 1–5 Feb | H4, H6 · *H2 (cont.)* | **Agent training on Chatwoot** | — | — |
| W20 | 8–12 Feb | Hardening, P9 on production | Content release 3 | — | Chatwoot live for the pilot |
| W21 | 15–19 Feb | Buffer, fixes | Launch communications ready | — | Two-week target measurement |
| W22 | 22–26 Feb | Buffer | — | — | ◆ **M6 full launch** go/no-go |

**If there's only one developer,** the italic tickets move after the main
column. Expect M2 to move to about W11, M4 to about W17, and M6 to about W24.
**If L2 slips past W14,** hold M4 and M5, and keep improving the website, since
nothing else is blocked.

---

## 13. Dependencies (the critical path in bold)

```
S1 ─► S3 ─► N7
S2 ─► C8
E2 ─► C2 ─► C3 ─► C6 ─► C8                     (conversation chain)
C1 ─► C4, C5, C7, C10, C11 ; K1 ─► C11, P3
E3 ─► N1 ─► N3 ─► N4 ─► N5 ─► (M2)             (understanding chain)
      N2 ─► N5, N6
P1 ─► P2 ─► P3 ─► W4 ─► W6, W7 ; P1 ─► P6 ─► W2 ─► W3 ─► W4
                    P3 ─► M2 ─► M4, M5 ; M2 ─► M1(App Review)
**Hosting procurement ─► P7 ─► M2, M3, M4**
**L2 legal ruling ─────────────────────────► M4, M5**
**W1 Meta verification + number ─► W7 templates ─► M4**
H1 ─► H2 ─► H4 ; P6 ─► H1, H6
```

---

## 14. Budget (to be confirmed with quotes)

| Item | Estimate | Notes |
|---|---|---|
| Production VM, Lusaka Tier III | **Get quotes** (Paratus, Infratel, MTN) | 2 vCPU / 4 GB is enough. A second VM for Chatwoot from W17. |
| WhatsApp messages | About US$14/month for 1,000 conversations, or about US$176/month for 10,000 | From the formula in `multi-platform-research.md` §8, using an illustrative US$0.004 per message. Replace it with the published Rest-of-Africa utility rate. |
| Meta Verified (optional) | Subscription | Only if the free blue badge is refused |
| Software licences | US$0 | Everything is open source: FastAPI, onnxruntime, MiniLM (Apache-2.0), dateparser, and self-hosted Chatwoot **[VERIFY edition]** |
| Engineering | About 100 developer-days | Plus a second developer from W06 (recommended) |
| Bank staff time | About 2 days/week (CO), 0.5 day/week (Legal), 0.5 day/week (CC), workshops | — |

---

## 15. Top schedule risks and the response

| Risk | Early warning | Response |
|---|---|---|
| The L2 legal ruling slips | Not scheduled by W04 | Escalate to the sponsor in W05. Launch the website (M3) regardless. |
| Hosting procurement slips | No contract by W05 | Temporary option: a Zambian cloud VM from the same providers. **Don't** fall back to hosting outside Zambia for real data. |
| Meta Business verification is rejected | Not verified by W06 | Fix the document mismatch (legal name, address) and resubmit. Meta's partner support is an option. |
| Messenger App Review is rejected | Rejection in W16–W17 | Resubmit with the screencast matching the use-case text exactly. M5 moves 2 weeks; nothing else depends on it. |
| One developer is overloaded | Two weeks behind at any milestone | Bring in the second developer. Cut C10 and N8, which are nice-to-have. |
| Holiday freeze is longer than assumed | O2 answer in W02 | Move M4 to after the freeze and spend the time on content and Messenger preparation |

The full risk register is in `excellence-plan.md` §9.

---

## Appendix A: ticket index

Status key: ☐ not started · ◐ in progress · ☑ done. Update it in the pull request
that finishes the ticket.

| ID | Title | Phase | Week | Size (days) | Depends on | Owner | Status |
|---|---|---|---|---|---|---|---|
| S1 | Urgent detection: recall and precision | 0 | W01 | 2 | — | Dev | ☑ |
| S2 | Fraud flow collects contact details | 0 | W01 | 1 | — | Dev | ☑ |
| S3 | Red-team routing suite | 0 | W01 | 1 | S1 | Dev | ☑ |
| E1 | CI on GitHub Actions | 0 | W01 | 0.5 | — | Dev | ☑ |
| E2 | Conversation test framework + 15 probe cases | 0 | W02 | 2 | — | Dev | ☑ |
| E3 | Evaluation gates (held-out + out-of-scope) | 0 | W02 | 1 | — | Dev | ☑ |
| E4 | Baseline metrics | 0 | W02 | 0.5 | E2, E3 | Dev | ☑ |
| P8 | Admin route auth | 0 | W02 | 0.5 | — | Dev | ☑ |
| C1 | System messages in YAML | 1 | W02 | 2 | — | Dev | ☑ |
| C2 | Typed commands anywhere | 1 | W03 | 1.5 | E2, C1 | Dev | ☑ |
| C3 | Answers to the bot's questions (yes/no, numbers, labels) | 1 | W03 | 2 | E2 | Dev | ☑ |
| C4 | Repair: repeat / what do you mean | 1 | W03 | 1.5 | C1, C2 | Dev | ☑ |
| C5 | Frustration detection | 1 | W04 | 1 | C1 | Dev | ☑ |
| C6 | In-flow digressions and corrections | 1 | W04–05 | 4 | C1, C3 | Dev | ☑ |
| C7 | Confirm before sending, and read-back | 1 | W05 | 2.5 | C1 | Dev | ☑ |
| C8 | Pre-fill the fraud flow | 1 | W06 | 3 | S2, C6 | Dev | ☑ |
| C9 | Context carry-over | 1 | W06 | 2 | — | Dev 2 | ☑ |
| C10 | Two questions in one message | 1 | W06 | 1.5 | C1 | Dev 2 | ☑ |
| C11 | Warmth: acknowledgements, name, category fallback | 1 | W06 | 2 | C1, K1 | Dev | ☑ |
| K1 | Short labels, simple answers, tone guide | 1 | W02–06 | — | — | CO | ☑ |
| K2 | Resolve the 17 `[CONFIRM` placeholders | 1–2 | W01–10 | — | — | Business | ☐ |
| N1 | Golden evaluation set pipeline and workshop | 2 | W04–07 | 1.5 | E3 | Dev + CO | ☐ |
| N2 | Out-of-scope set (≥ 300) | 2 | W07 | 1 | — | Dev + CO | ☐ |
| N3 | Local embedding model in the matcher | 2 | W07–08 | 4 | E3, N1 | Dev | ☐ |
| N4 | Shadow mode and report | 2 | W08 | 2 | N3 | Dev | ☐ |
| N5 | Threshold calibration | 2 | W09 | 1.5 | N1–N3 | Dev | ☐ |
| N6 | Out-of-scope intent | 2 | W08 | 1.5 | N2 | Dev + CO | ☐ |
| N7 | Model-based second urgent check | 2 | W09 | 1.5 | N3, S1 | Dev | ☐ |
| N8 | Code-mixed phrases and multilingual test | 2 | W09 | 1 | N1 | Dev | ☐ |
| P1 | Persistent session store | 3a | W07 | 3 | — | Dev 2 | ☑ |
| P2 | Channel interface; move `/chat` | 3a | W10 | 2 | P1 | Dev 2 | ☑ |
| P3 | Renderer and per-channel limit tests | 3a | W10–11 | 4 | P2, K1 | Dev 2 | ☑ |
| P4 | Per-channel kill switches, per-user limits | 3a | W11 | 1.5 | P2 | Dev 2 | ☑ |
| P5 | Fewer message bubbles | 3a | W11 | 1 | — | Dev 2 | ☑ |
| P6 | Audit channel column and HMAC identities | 3a | W08 | 2 | P1 | Dev 2 | ☑ |
| P7 | Lusaka production hosting and runbook | 3a | W09–10 | 3 | Procurement | Dev 2 | ☐ |
| P9 | Load and soak test | 3a | W10, W20 | 1 | P1, P7 | Dev | ☐ |
| W1 | Meta onboarding | 3b | W01–12 | — | — | PO | ☐ |
| W2 | WhatsApp webhook (signature, inbox, worker) | 3b | W11 | 3 | P2, P6 | Dev | ☑ |
| W3 | WhatsApp inbound parser | 3b | W12 | 2 | W2 | Dev | ☑ |
| W4 | WhatsApp sender | 3b | W12 | 3 | P3, W3 | Dev | ☑ |
| W5 | Media and voice-note policy | 3b | W13 | 1 | W3 | Dev | ☑ |
| W6 | Location-based branch finder | 3b | W13 | 1.5 | W4 | Dev + Ops | ☑ |
| W7 | Utility templates | 3b | W14 | 1 | W4, L6 | Dev + Legal | ☐ |
| W8 | 24-h window and stale messages | 3b | W12 | 1.5 | W2, P1 | Dev 2 | ☑ |
| W9 | WhatsApp content variants | 3b | W12 | 0.5 | P3 | Dev 2 + CO | ☐ |
| W10 | Pilot runbook | 3b | W14–17 | — | — | PO + CC | ☐ |
| M1 | Messenger App Review pack | 3c | W15 | 1 | M2 | PO + Legal | ☐ |
| M2 | Messenger adapter | 3c | W15 | 3 | P2, P3 | Dev | ☐ |
| M3 | Page profile (Get Started, menu, ice breakers) | 3c | W15 | 1 | M2 | Dev | ☐ |
| M4 | Handover to the Page Inbox | 3c | W18 | 2.5 | M2, H1 | Dev | ☐ |
| M5 | Private replies to urgent comments | 3c | W17 | 2 | M2, S1 | Dev + SM | ☐ |
| H1 | Tickets carry channel and reply address | 4 | W15 | 1 | P6 | Dev 2 | ☐ |
| H2 | Chatwoot agent desk | 4 | W17–19 | 6 | H1, W4, M2 | Dev 2 | ☐ |
| H3 | Opening hours and out-of-hours promises | 4 | W16 | 1 | O1 | Dev 2 | ☐ |
| H4 | "Bot got this wrong" loop | 4 | W19 | 1.5 | H2, N1 | Dev | ☐ |
| H5 | Sampled CSAT | 4 | W17 | 1.5 | — | Dev | ☐ |
| H6 | Quality report v2 | 4 | W19 | 2 | P6, C2–C11 | Dev | ☐ |
| R1 | Runbooks and alerts | 4 | W14 | 2 | P7 | Dev + PO | ☐ |
| R2 | Go/no-go checklists | 4 | W10–22 | — | — | PO | ☐ |
| L1–L8, H-P, O1, O2, MK1 | Non-engineering tracks (§10) | — | W01+ | — | — | As listed | ☐ |

**Engineering total ≈ 101 developer-days.**

## Appendix B: the ticket-to-target map

This shows which tickets move each target in `excellence-plan.md` §1.

| §1 target | Moved by |
|---|---|
| Fraud recall 100%, with contact details on every fraud ticket | S1, S2, S3, N7 |
| Out-of-scope direct answers ≤ 3% | N2, N3, N5, N6, E3 |
| Direct answers right ≥ 85%, wrong ≤ 2% | N1, N3, N5, C9, K1 |
| 15/15 probe cases, and 0 re-asks | C2–C11, E2 |
| Human reachable from every state; SLA ≥ 95% | C2, M4, H1–H3 |
| ≤ 4 bot messages per conversation | P5, C8, C10 |
| Delivery failures ≤ 1% | W2, W4, W8, R1 |
| CSAT ≥ 4.2 | H5, and everything above |
