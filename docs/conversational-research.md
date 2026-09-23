# Making the bot more conversational: research and plan

**What public repos teach, where our bot falls short today, and how to close the gap**

Researched 2026-09-23 · Status: research and recommendation. No application code changed yet.

> **How to read this.** §1 is the one-page answer. §2 lists the public repos
> worth learning from and what to take from each. §3 shows where the current bot
> breaks, measured by driving `router.handle()` with 15 realistic conversational
> moves. §4–§6 are the plan, in three tiers ordered by legal risk. §7 covers how
> to measure progress, and §8 is the roadmap.
>
> **Method.** Four sources are quoted from their source code rather than from
> summaries. Rasa Pro 3.20.0, Parlant 3.3.2 and semantic-router 0.1.16 were
> downloaded from PyPI and read directly. dateparser 1.4.3 was installed and run
> against fraud-flow inputs. Everything else comes from web research, cited in
> §9. GitHub itself couldn't be browsed from the research environment. Anything
> marked **[VERIFY]** needs checking before a decision depends on it.

---

## 1. The one-page answer

**"More conversational" mostly doesn't mean "add an LLM".** What makes a bot feel
like it's listening is how it handles the moves people make *other than
answering the question*:

- correcting themselves ("sorry, my number is actually…")
- asking something mid-form ("what time do you close?")
- saying "yes" to a question the bot asked
- typing "cancel" or "talk to a person"
- not understanding the bot ("what do you mean?")
- giving everything at once ("I lost my card yesterday at Cairo")
- getting frustrated without swearing

The mature public frameworks all converge on the same short list of these
**conversation-repair patterns**. Rasa Pro 3.20.0 ships 21 of them as built-in defaults.
Microsoft's samples handle "interruptions". IBM's Natural Conversation Framework
derives them from conversation-analysis research.

**Where we are.** In a probe of 15 such moves, the bot handled **3 well** and got
through **2 by luck**. It **failed visibly on 10**. It stored "cancel" as the customer's name, recorded
"sorry my number is actually 0966…" as the callback *topic*, trapped a customer
who asked a question mid-form in a "that doesn't look like a valid number" loop,
and counted "yes" as a failed guess.

**The plan, in three tiers ordered by legal risk:**

1. **Tier 1: deterministic conversation patterns** (§4). No machine learning, no
   new data leaving the server, and every reply still comes from approved text.
   This fixes most of the probe failures and is the biggest win for the effort.
   It sits within the V1 "no LLM" rule.
2. **Tier 2: better understanding with local, non-generative models** (§5).
   Sentence embeddings or SetFit, running on our own server, still only *choose*
   between approved answers. This improves paraphrase and negation handling. It
   needs a light legal check, but not the V2 LLM ruling.
3. **Tier 3: an LLM for understanding only, never for writing** (§6). This is V2,
   after the legal ruling. Either use Rasa's "command generator" pattern, where
   the LLM emits structured commands and the replies stay templated, or Parlant's
   *strict* mode, where the LLM may only choose from approved replies and I
   verified in its source that any other output is rejected. Free generation of
   regulated content stays off.

**A safety bug the probe found**, separate from conversational polish: the urgent
scan in `guards.urgent_scan` returns `None` for "someone stole money from my
etumba", "they stole my money" and "someone took money from my account". The first
of these only reached the fraud flow because the fuzzy matcher happened to pick
the *lost card* intent, and the customer was then told "let's secure your card
straight away". Fix this first (§8, step 0).

---

## 2. Public repos worth learning from

### 2.1 Dialogue frameworks with conversation repair built in

| Repo | What it is | What to take from it | Status / licence |
|---|---|---|---|
| **[RasaHQ/rasa](https://github.com/RasaHQ/rasa)** plus **Rasa Pro (CALM)** | The best-known open conversational framework. CALM, its current architecture, is in Rasa Pro. | Its **default conversation-repair patterns**, read from `default_flows_for_patterns.yml` in the 3.20.0 wheel: cancel, correction, clarification, chitchat, completed ("anything else?"), continue-interrupted (resume after a digression), repeat bot messages, skip question, cannot-handle, human handoff, internal error, session start/end, restart, validate slot, customer satisfaction. This is our checklist (§4). | Open-source `rasa` 3.6.21 (Jan 2025, Apache-2.0) looks to be in maintenance mode. Rasa Pro 3.20.0 (21 Sep 2026) has visible source, a **free developer licence with limited production use**, and a paid licence for scale. Take the pattern *design*, not the code. |
| **[RasaHQ/rasa-calm-demo](https://github.com/RasaHQ/rasa-calm-demo)** | Reference assistant for CALM | Worked examples of overriding patterns in `data/flows/patterns.yml`, e.g. custom wording for corrections and cancels | Active |
| **[RasaHQ/financial-demo](https://github.com/RasaHQ/financial-demo)** | A banking assistant: balance, transfers, card lock | Switching context **mid-form and returning to the original task**, plus a simple human-handoff skill. The closest domain match to us. | Older Rasa 2/3 era. Good for reading, not to run. |
| **[microsoft/BotBuilder-Samples](https://github.com/microsoft/BotBuilder-Samples)** | Bot Framework samples | `CancelAndHelpDialog` shows two kinds of interruption. A *turn-level* one answers help, keeps the form's state and resumes next turn. A *dialog-level* one cancels. That's exactly the digression-versus-cancel split we need. | **Archived.** Support ended 31 Dec 2025, and the successor is the Microsoft 365 Agents SDK. Still good for reading. |
| **[theopenconversationkit/tock](https://github.com/theopenconversationkit/tock)** | An open conversational platform (Kotlin), started at SNCF | A French bank, Crédit Mutuel Arkéa, maintains a public fork, which is useful evidence that banks run open-source dialogue platforms | Active (Aug 2026) |
| [deeppavlov/DeepPavlov](https://github.com/deeppavlov/DeepPavlov) | An NLP and dialogue framework | Component ideas only | Last PyPI release Aug 2024 |
| [botpress/botpress](https://github.com/botpress) | A bot builder | Not recommended: the self-hosted v12 line has had no release since 2023, and new features ship to the cloud product | Stale open source |

### 2.2 Controlling LLMs in customer-facing chat (for V2)

| Repo | What it is | What to take from it | Status / licence |
|---|---|---|---|
| **[emcie-co/parlant](https://github.com/emcie-co/parlant)** | A "control harness" for customer-facing LLM agents: guidelines, journeys, canned responses | **Composition modes**, read from `parlant/core/agents.py`: `fluid`, `canned_fluid`, `canned_composited` and `canned_strict`. In **strict** mode, `canned_response_generator.py` rejects any LLM output that isn't in the approved list and sends a no-match message instead. The strictest mode matched by any guideline wins. This is the model for "an LLM that can't say anything legal hasn't approved". | 3.3.2 (Apr 2026), Apache-2.0 |
| **[NVIDIA-NeMo/Guardrails](https://github.com/NVIDIA-NeMo/Guardrails)** | Programmable rails around LLMs, written in the Colang language | *Dialog rails* map user messages to "canonical forms" and pick a predefined reply where one exists. *Topical rails* keep the bot on scope. | 0.24.1 (16 Sep 2026), Apache-2.0 |
| Rasa's **Contextual Response Rephraser** | An LLM rewrites a templated reply "in context" | Rasa's own docs warn that the rephrasing *may not preserve the exact meaning* of the template. **Don't use it for regulated facts.** At most, consider it later for neutral connective phrases. | Part of Rasa Pro |
| Rasa's **LLM command generator** | An LLM turns each message into commands, not text. The command classes in the 3.20.0 source are `StartFlow`, `SetSlot`, `CorrectSlots`, `Clarify`, `CancelFlow`, `ChangeFlow`, `SkipQuestion`, `RepeatBotMessages`, `ChitChatAnswer`, `KnowledgeAnswer` and `CannotHandle`. Handing over to a human is done by a *pattern* (`pattern_human_handoff`), not a command. | Invalid commands are discarded and the command output is never shown to users. That keeps all behaviour inside business logic. Rasa also publishes fine-tuned **Llama 3.1 8B** command-generator models on Hugging Face, which could be **hosted locally** and so matter for data residency (see the multi-platform research). | Rasa Pro licence for the framework. Check each model's licence separately **[VERIFY]**. |

### 2.3 Understanding without generating (Tier 2)

| Repo | What it is | Why it fits us | Status / licence |
|---|---|---|---|
| **[aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router)** | Routes a message to a "route" (for us, an intent) by embedding similarity against example phrases. No LLM and no prompt. It returns *no route* below a score threshold. | This is the same shape as our `phrases:` lists, and the same idea as our confidence thresholds. It supports **local** encoders (Hugging Face, fastembed, local, TF-IDF, BM25 — I checked `encoders/` in 0.1.16), so nothing leaves the server. | 0.1.16 (Jul 2026), MIT |
| **[huggingface/setfit](https://github.com/huggingface/setfit)** | Few-shot text classification on top of sentence transformers, needing about 8 examples per class and no prompts | Our intents already have 8–15 phrases each. Multilingual checkpoints exist, which helps with Bemba/Nyanja mixing later. | 1.2.0 (Sep 2026), Apache-2.0 |
| [sentence-transformers](https://github.com/UKPLab/sentence-transformers) | The embedding library underneath both of the above | Use it directly if we don't need the extra layers | 6.1.0 (Sep 2026), Apache-2.0 |
| **[scrapinghub/dateparser](https://github.com/scrapinghub/dateparser)** | Parses relative dates ("yesterday", "2 days ago", "on Monday") | Can normalise the fraud flow's "When did this happen?" answers. **Tested:** it handles today, yesterday, "2 days ago", "on Monday", "3rd september" and DMY dates. It returns *None* for "this morning", "last night", "last friday" and "sometime last week", and **misreads "10am" as 10 September** when searching inside a sentence. So **keep the customer's own words**, and add the parsed date only as a hint for staff. | 1.4.3 (Sep 2026), BSD-3 |
| [facebook/duckling](https://github.com/facebook/duckling) | A rule-based extractor for time, number and amount-of-money | Stronger on times than dateparser, but it's Haskell and runs as a separate service, so it's heavier to run | BSD-style **[VERIFY]** |
| [microsoft/Recognizers-Text](https://github.com/microsoft/Recognizers-Text) | Number, date and phone recognisers (they power LUIS) | Good design, but the **Python package was last released in 2019**, so avoid it | MIT, stale on Python |

### 2.4 Data and evaluation

| Repo / dataset | What it is | How we'd use it | Licence |
|---|---|---|---|
| **[BANKING77](https://github.com/PolyAI-LDN/task-specific-datasets)** (PolyAI) | 13,083 real-style online-banking queries across 77 fine-grained intents | Map the overlapping intents (card lost or stolen, transfer issues, top-ups, fees, PIN…) to ours. The result is a **held-out paraphrase test set** that shows how our matcher copes with wording nobody on the team wrote. | CC BY 4.0 (commercial use OK with attribution) |
| **[clinc/oos-eval](https://github.com/clinc/oos-eval)** (CLINC150) | 150 intents plus explicit **out-of-scope** queries | Use the out-of-scope queries to measure the **dangerous** failure for a bank: a confident answer to something the bot doesn't cover | **[VERIFY licence]** |
| [jianguoz/Few-Shot-Intent-Detection](https://github.com/jianguoz/Few-Shot-Intent-Detection) | Standard intent datasets with out-of-scope splits, plus baselines | Benchmark our matcher against published numbers | **[VERIFY]** |
| **[sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench)** | Customer-service agent evaluation with **LLM-simulated users**. It introduces **pass^k**: does the agent succeed on *every one* of k runs, not just once? | Borrow the method, offline and with synthetic personas only: simulated customers who digress, correct themselves and get frustrated. It's also a consistency metric for V2. | **[VERIFY]** |
| [Botium](https://github.com/codeforequity-at/botium-docs) | "Convo" files describing expected conversations for chatbot regression tests | The *convo-file idea*. Our pytest suite can express it directly (§7). | Open-source core; the commercial product is now part of Cyara |
| [facebookresearch/EmpatheticDialogues](https://github.com/facebookresearch/EmpatheticDialogues) | 25k empathetic conversations across 32 emotions | Read for tone patterns only. **Licence likely non-commercial [VERIFY]**, so don't train on it. | — |
| [unza-speech-lab/zambezi-voice](https://github.com/unza-speech-lab/zambezi-voice) | Speech corpus for Bemba, Nyanja, Tonga, Lozi (79 h labelled) from the University of Zambia | Relevant to future voice-note and local-language work, but **CC BY-NC-ND 4.0: no commercial use, no derivatives**, so it's research only. Local-language support will need the bank's own data. | CC BY-NC-ND 4.0 |

### 2.5 Design knowledge (research, not code)

- **IBM Natural Conversation Framework** (Robert J. Moore and Raphael Arar). A
  pattern language of **100 interaction patterns** drawn from conversation
  analysis, built around "expandable sequences" and repair. Their key point is
  that bots ask *users* to rephrase, but rarely let users repair *the bot's*
  turn. Examples are "what do you mean?", "say that again", "can you give an
  example?" and "what does X mean?". Their 2019 work documents nine such
  user-initiated repair types.
- **Nielsen Norman Group chatbot guidelines.** State the scope up front, allow
  both buttons and free text, design for error recovery, and don't make users
  repeat information.
- **The CFPB's review of bank chatbots.** Its central finding is "doom loops"
  with no way out to a human. The bot's two-strike rule and always-available
  "Talk to a person" already address this, but the probe (§3) shows typed escape
  words don't work mid-flow.
- Curated lists: [awesome-conversational-ai](https://github.com/jyguyomarch/awesome-conversational-ai)
  and [awesome-chatbots](https://github.com/JStumpp/awesome-chatbots).

---

## 3. Where the current bot breaks

I drove `router.handle()` directly (with a temporary data directory, and repo
data untouched) using 15 moves real customers make. ✅ means handled well, ⚠️ means
it passed only by luck, and ❌ means the customer would notice a failure.

| # | Move | What the user said | What the bot did | |
|---|---|---|---|---|
| 1 | Follow-up that depends on context | "what is tamanga" → "how much does it cost" → "what do i need to open it" | Gave the *generic* fee list and the generic requirements. It ignores `session.slots["topic"]`. | ⚠️ |
| 2 | Over-informative first message | "I lost my card yesterday at cairo branch" | Started the fraud flow, then asked "Please tell me briefly what happened." It asks again for facts the first message already gave. | ❌ |
| 3 | Correction mid-form | (callback flow) "sorry my number is actually 0966123456" | Saved it as the callback **topic**, and the wrong number stays on the ticket | ❌ |
| 4 | A question in the middle of a form | (at the phone step) "what are your opening hours?" | "That doesn't look like a valid number…", **twice**. The customer is trapped until they cancel. | ❌ |
| 5 | A question inside the fraud flow | "what is the emergency number?" | Saved as `what_happened` and moved on to "When did this happen?" | ❌ |
| 6 | Typed "cancel" mid-form | "cancel" | Saved as the customer's **name**: `{'name': 'cancel'}` | ❌ |
| 7 | Typed "talk to a person" mid-flow | (complaint flow) "talk to a person" | Saved as the complaint topic. Only the *button* escapes a flow. | ❌ |
| 8 | Two questions at once | "what are your opening hours and where is the kitwe branch" | "Did you mean…?" with *Find a branch* and *Opening hours*. Reasonable, but neither gets answered. | ⚠️ |
| 9 | Repairing the bot's turn | "what do you mean?" / "say that again" | Answered the "what can you do?" intent, then a "Did you mean…?" | ❌ |
| 10 | Numbered reply | "2" | A fallback, which **counts as a strike** | ❌ (and needed for WhatsApp) |
| 11 | Greeting plus request | "hi, I want to open an account" | The correct answer | ✅ |
| 12 | Negation | "I don't want a loan, I want to open an account" | The correct answer (0.81) | ✅ |
| 13 | Frustration without swearing | "this is not helping" / "you are not understanding me" | Suggested "What can you do?", then a fallback. That's tone-deaf. | ❌ |
| 14 | "yes" to "anything else?" | "yes" after the callback confirmation | A fallback, which **counts as a strike**: the customer is penalised for answering our question | ❌ |
| 15 | Out-of-scope balance request | "can i check my balance" | The eTumba `*888#` balance answer | ✅ |

**Urgent-scan check:** `guards.urgent_scan()` returns `None` for:

- "someone stole money from my etumba"
- "they stole my money"
- "someone took money from my account"

`FRAUD_RE` has *stolen* and *theft* but not *stole*, and `FRAUD_PHRASES` needs
the exact "took my money". Case 5 only started the fraud flow because the matcher
picked `lost_stolen_card` at 0.718, so the customer got the lost-*card* intro for
an eTumba theft.

**What the failures have in common:** `FormFlow.handle()` treats **every** input
as the answer to the current step. Nothing checks first whether the message is
really an answer, a correction, a question, or a request to leave. Fixing that
one assumption fixes cases 3–7 (§4.2).

---

## 4. Tier 1: deterministic conversation patterns (V1-compatible)

Everything here is rules plus approved text. There's no machine learning and no
new data flow, so it's compatible with V1's "no LLM" scope. Each item names the
pattern it borrows.

### 4.1 Global commands, recognised in any state *(Rasa: cancel, human handoff, restart, repeat; Microsoft: dialog-level interruption)*

Recognise typed commands **as if they were button payloads**, before the active
flow consumes the text. That means adding them in `router._route()` alongside
the existing `menu`, `cancel_flow` and `human_handoff` payload checks.

- **Whole-message match only.** Recognise "cancel", "stop", "never mind",
  "menu", "start again", "agent", "talk to a person", "human", "0" (for
  WhatsApp) and "help". Never use substrings. "Cancel my card" is in
  `LOST_CARD_PHRASES` and must still go to the fraud flow.
- **Order is load-bearing.** Commands go *after* the urgent-topic scan for
  anything fraud-shaped, so "stop, someone is stealing my money" still triggers
  the fraud flow. A bare "stop" cancels.
- **Mid-fraud or mid-complaint,** "cancel" should confirm first ("Your report
  isn't sent yet. Stop anyway? [Yes, stop] [No, continue]"), because abandoning a
  fraud report is costly.

This fixes cases 6 and 7, and makes WhatsApp workable once buttons scroll away.

### 4.2 Classify every in-flow message before storing it *(Rasa: continue-interrupted, correction, skip; Microsoft: turn-level interruption)*

Replace "every input is the answer" in `FormFlow.handle()` with a small
classifier that runs first.

```
in-flow message ──► 1. command?      (4.1)           → handle it
                    2. correction?   (4.3)           → update the earlier field, confirm, re-ask the current step
                    3. digression?   question-shaped AND matcher ≥ HIGH_CONFIDENCE
                                     on a non-flow intent → answer it, then
                                     "Now, back to your callback: <current prompt>"
                    4. otherwise     → it's the answer (validator as today)
```

- A message counts as **question-shaped** if it ends with "?" or starts with a
  question word (what, when, where, how, can, do, is…). Require high confidence
  so a free-text answer ("they took money when I was at the ATM") isn't treated
  as a question.
- **Validator steps** (phone number) make this almost free. If the input fails
  the validator *and* looks like a question, it's a digression, not a bad number.
  That fixes case 4.
- **Free-text steps** in the fraud and complaint flows: only treat a message as a
  digression if it's question-shaped *and* the match is high-confidence, and
  always return to the report afterwards (case 5). **Never let a digression end a
  fraud report.**
- **State:** there's no stack yet. Store `session.flow_state["interrupted_at"]`
  so the re-prompt uses `flow.resume()`, which already exists for page reloads.

### 4.3 Corrections, read-backs and confirmation *(Rasa: correction + `utter_corrected_previous_input`; IBM NCF: confirmation)*

- **Detect a correction** when the message contains a marker ("sorry", "actually",
  "I meant", "wrong", "not X but Y", "my number is") *and* a value that passes an
  **earlier** step's validator. For example, a valid Zambian phone number arriving
  at the topic step is a phone correction. Update that field, then reply with
  approved text: "Thanks, I've updated your number to 0966 123 456." Then re-ask
  the current step. That fixes case 3.
- **Read critical values back** as you go: "Got it: 0977 123 456." If the
  customer misread their own number, they can fix it immediately.
- **Confirm before the ticket goes out** in the lead and complaint flows: "Here's
  what I'll send: Mary Banda · 0977 123 456 · about a loan · morning. [Send it]
  [Change something]". For the fraud flow, keep speed over polish and show the
  summary in the confirmation message instead of asking a question.

### 4.4 Pre-fill from what the customer already said *(Rasa: `SetSlot` at `StartFlow`, and the `ask_before_filling` flag)*

A trigger message like "I lost my card yesterday at cairo branch" often contains
the answer to every step of the fraud flow.

- **`what_happened`**: the message that triggered the flow already *is* the
  description. Store it, so the flow doesn't ask for it again.
- **`when`**: first a small keyword list (today, this morning, last night,
  yesterday, weekday names), then `dateparser` as a **hint only**. Keep the raw
  words and never overwrite them, because the dateparser test in §2.3 showed real
  misses and one silent misread.
- **`channel`**: keywords such as etumba, card, atm, internet/online banking,
  MyABZ, branch, and the branch names from `branches.json`.
- **Confirm rather than assume.** For example: "You said this happened yesterday,
  involving your card. Is that right? [Yes] [No, let me explain]". That turns
  three questions into one confirmation (case 2) and saves billable WhatsApp
  messages.

### 4.5 Contextual yes/no, numbered replies and "anything else?" *(Rasa: completed, and the `continue_conversation` slot)*

- When a bot message asks a question, store what each answer means:
  `session.expecting = {"yes": <payload>, "no": <payload>, "options": [...]}`.
- Then interpret the next message against it:
  - yes: "yes", "yeah", "yes please", "ok", "sure"
  - no: "no", "no thanks", "that's all"
  - a number or number word: "1", "2", "one", "two"
  - a button label typed out

  Map each to the stored payload *before* the matcher runs. That fixes cases 10
  and 14. A "yes" should never cost a strike.
- Clear `expecting` on any other input, so a stale "yes" can't fire later.

### 4.6 Let customers repair the bot's turn *(IBM NCF user-initiated repair; Rasa: repeat bot messages)*

- Recognise "what do you mean", "I don't understand", "huh", "say that again",
  "repeat", "explain" and "example?".
- For "repeat": resend the last bot message from `session.transcript`.
- For "what do you mean": send the intent's optional **`answer_simple`**, a
  shorter, plainer, *legally approved* version of the answer written in the
  YAML. If there isn't one, fall back to repeating plus a "Talk to a person"
  button. That fixes case 9.

### 4.7 Frustration without swearing

- Extend `guards.is_abusive()` into a separate `is_frustrated()`. Match phrases
  like "not helping", "you don't understand", "I already told you", "waste of
  time", "!!!" and all-caps messages.
- Route these to the existing calm-plus-human response, with a gentler text than
  the abuse one, and **don't count a strike**. That fixes case 13.
- Grow the phrase list from real transcripts each week, the same loop as the
  abuse list.

### 4.8 Context carry-over *(Dialogflow-style "input contexts"; Rasa slots)*

- Declare follow-ups in the YAML. For example, `current_account` could have
  `follow_ups: {fees: fees_tamanga, requirements: account_opening_requirements}`.
- When the next message is short, uses a pronoun ("it", "that", "this account")
  or is generic ("how much", "what do I need"), and the matcher's top intent is a
  generic sibling, prefer the follow-up for the current topic. That fixes case 1.
- Keep it inspectable: log `context_boost` in the audit metadata, so every
  context-driven decision can be traced.

### 4.9 Two questions in one message

- Split on " and ", " also " and "?" into at most two clauses, and match each one.
- If **both** match with high confidence, answer both in **one** message (one
  billable WhatsApp message, not two).
- Otherwise keep today's "Did you mean…?". That improves case 8.

### 4.10 Warmth that doesn't touch the facts

- Use the customer's name once the lead flow has it ("Thanks, Mary").
- Add short **acknowledgement variants** ("Got it.", "Thanks.", "Okay.") and
  rotate them deterministically, e.g. by turn number, so the bot doesn't sound
  robotic. Only the *wrappers* vary. Facts and figures come from the single
  approved answer.
- Make fallbacks say what *was* understood. With a medium-confidence category,
  that could be "I can see this is about loans. Which of these is closest?"
  rather than a generic "I didn't quite catch that".

### 4.11 Move built-in wording into YAML so legal can review it

New conversational text (acknowledgements, correction confirmations, the "back to
your callback" line, frustration replies) is customer-facing wording. Today the
router's texts (`WELCOME_TEXT`, `FALLBACK_TEXT`, etc.) and the flow prompts live
in Python, and `admin/legal_export.py` only *points at* the flow files rather
than exporting them. Put all built-in texts in `knowledge/system_messages.yaml`
so they go through the same review, git history and export as the answers.

---

## 5. Tier 2: better understanding with local, non-generative models

**The goal:** handle paraphrases, negation and unusual wording better than
character-level TF-IDF plus fuzzy matching, while the output is still *an
intent*. The customer still receives only approved text.

- **Approach.** Embed each intent's `phrases:` with a small sentence-transformer,
  either through semantic-router's local encoder or directly. Alternatively,
  train a SetFit classifier on the same phrases. Then **blend** the result with
  the current score in `app/matcher.py` instead of replacing it: character
  n-grams still help with misspellings, and embeddings help with meaning. Keep
  `HIGH_CONFIDENCE`/`MEDIUM_CONFIDENCE` and recalibrate them.
- **It runs on our server on CPU**, with no external API, which keeps the
  §3/data-residency position unchanged. Pin the model files by checksum in the
  repo's deploy process, because a model swap changes behaviour just as a content
  edit does, and it should be tested the same way.
- **Adopt it only if it wins on both sides** of the evaluation in §7:
  1. accuracy on held-out *in-scope* paraphrases (from BANKING77 intents mapped
     to ours, plus real unmatched transcripts);
  2. **no increase in confident wrong answers** on *out-of-scope* queries (from
     CLINC150's out-of-scope set).

  For a bank, the second number matters more.
- **Language mixing** (Bemba/Nyanja/English). Multilingual checkpoints exist, but
  the only Zambian-language corpus found (Zambezi Voice) is non-commercial. Plan
  to collect phrases from the bank's own transcripts and social-media team.
- **Legal position.** This is statistical matching, not generative AI, but it's
  still a model making routing decisions. Brief legal before shipping and log
  scores as today, so every decision stays auditable.

---

## 6. Tier 3: an LLM for understanding, never for regulated wording (V2)

This happens only after the legal ruling the README already requires for V2.
Here are the four patterns the public repos offer, from safest to riskiest:

| Pattern | Example | What the customer sees | Fit for AB Bank |
|---|---|---|---|
| **A. LLM as understanding only** | Rasa's command generator: the LLM outputs `StartFlow` / `SetSlot` / `CorrectSlots` / `Clarify` / `CancelFlow` commands, validated against a schema, with invalid output discarded | Only approved templates | **Best first V2 step.** It makes §4's corrections, digressions and pre-filling robust to any wording. It could run on a **locally hosted** model (Rasa publishes fine-tuned Llama 3.1 8B command generators), which matters for data residency. |
| **B. LLM chooses, never writes** | Parlant `canned_strict`: output not in the approved set is rejected (verified in source) | Only approved templates | Good for choosing among close answers and for natural-feeling transitions from an approved list |
| **C. LLM rephrases approved text** | Rasa's Contextual Response Rephraser | *Rewritten* text | **Not for facts, fees or procedures.** Rasa itself warns the meaning may drift. At most, use it for neutral acknowledgements, with a separate approval. |
| **D. Free generation / RAG** | Typical LLM chatbots | Model-written text | Out of scope until there's a much stronger governance story. Fraud and complaint flows stay deterministic forever. |

These rules apply to every V2 pattern:

- The existing invariants hold. `guards.mask()` runs **before** any model call,
  so a model only ever sees masked text.
- Urgent-topic handling stays rule-based, with the LLM as a second layer only.
- Every LLM decision is logged.
- NeMo Guardrails-style topical rails keep the model on scope.
- WhatsApp's 2026 policy allows AI used for the business's own customer service
  (see `docs/multi-platform-research.md` §2).

---

## 7. How to measure "more conversational"

1. **Turn §3 into a regression suite** (`tests/test_conversation.py`). Each of the
   15 moves becomes a scripted conversation that asserts on behaviour: what gets
   stored, whether a strike is counted, and whether the flow resumes. Start the
   failing cases as `xfail(strict=True)`, so each one turns into a real pass as
   it's fixed and can't silently regress. This is Botium's "convo file" idea in
   plain pytest, and Rasa calls the practice "conversation-driven development".
2. **Held-out language sets** (§5): in-scope paraphrases and out-of-scope
   queries, scored on every matcher change. Report accuracy *and* the rate of
   confident wrong answers.
3. **Conversation-level metrics** in `admin/report.py`, per channel:
   - **re-asks**: questions asking for something the customer already said
   - repairs, and whether each succeeded
   - corrections applied
   - digressions resumed versus abandoned
   - strikes per conversation
   - flow completion rate and cancel rate
   - handoffs that follow frustration
4. **Simulated customers, offline** (tau2-bench method). This is an optional V2
   tool. Scripted or LLM-played personas (the digressor, the corrector, the
   over-sharer, the frustrated customer, the code-switcher) run hundreds of
   synthetic conversations against the bot. Measure **pass^k**: does the bot
   handle a persona *every* time, not just once? Use synthetic data only, never
   real transcripts.

---

## 8. Roadmap

| Step | What | Fixes | Size |
|---|---|---|---|
| **0 (do first, safety)** | Widen `guards.urgent_scan()`: add *stole*, "took money from", "money was taken", "someone took". Pick the fraud intro by what was stolen (card versus money/eTumba) so an eTumba theft doesn't get "secure your card". Add red-team cases. | The urgent-scan misses | Small |
| 1 | The §3 probe becomes `tests/test_conversation.py` (xfail where failing) | Measurement | Small |
| 2 | Global commands (4.1), contextual yes/no and numbered replies (4.5), repair and repeat (4.6), frustration (4.7) | Cases 6, 7, 9, 10, 13, 14 | Small–medium |
| 3 | In-flow message classification: digressions and corrections, plus read-back and confirmation (4.2, 4.3) | Cases 3, 4, 5 | Medium |
| 4 | Pre-filling (4.4), context carry-over (4.8), two-question splitting (4.9), warmth (4.10), system messages in YAML (4.11) | Cases 1, 2, 8 | Medium |
| 5 | An offline Tier 2 experiment: embeddings or SetFit blended with the current matcher, judged on the §7 evaluation sets | Paraphrase robustness | Medium |
| 6 (V2, after the legal ruling) | Pattern A (LLM as understanding only), piloted against the same suite | Robustness to any wording | Large |

Steps 0–4 need no ML and fit the current architecture. Steps 2–4 also make the
WhatsApp and Messenger channels in `docs/multi-platform-research.md` work,
because on messaging apps customers type rather than tap, and buttons scroll out
of view.

---

## 9. Sources

**Frameworks and repos**

- [RasaHQ/rasa](https://github.com/RasaHQ/rasa)
- [Rasa: conversation patterns](https://rasa.com/docs/rasa-pro/concepts/conversation-repair/)
- [RasaHQ/rasa-calm-demo](https://github.com/RasaHQ/rasa-calm-demo)
- [rasa-calm-demo `patterns.yml`](https://github.com/RasaHQ/rasa-calm-demo/blob/main/data/flows/patterns.yml)
- [RasaHQ/financial-demo](https://github.com/RasaHQ/financial-demo)
- [Rasa: LLM command generators](https://rasa.com/docs/reference/config/components/llm-command-generators/)
- [Rasa command-generator model (Llama 3.1 8B)](https://huggingface.co/rasa/command-generator-llama-3.1-8b-instruct)
- [Rasa: Contextual Response Rephraser](https://rasa.com/docs/reference/primitives/contextual-response-rephraser/)
- [emcie-co/parlant](https://github.com/emcie-co/parlant)
- [NVIDIA-NeMo/Guardrails](https://github.com/NVIDIA-NeMo/Guardrails)
- [NeMo Guardrails: dialog rails](https://docs.nvidia.com/nemo/guardrails/latest/colang-2/getting-started/dialog-rails.html)
- [microsoft/BotBuilder-Samples](https://github.com/microsoft/BotBuilder-Samples)
- [Microsoft: handle user interruptions](https://learn.microsoft.com/en-us/azure/bot-service/bot-builder-howto-handle-user-interrupt?view=azure-bot-service-4.0)
- [Bot Framework SDK end-of-support notice](https://devblogs.dewiride.com/ai/microsoft-365-agents-sdk/end-of-microsoft-bot-framework-sdk)
- [theopenconversationkit/tock](https://github.com/theopenconversationkit/tock)
- [CreditMutuelArkea/tock](https://github.com/CreditMutuelArkea/tock)
- [deeppavlov/DeepPavlov](https://github.com/deeppavlov/DeepPavlov)
- [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router)
- [huggingface/setfit](https://github.com/huggingface/setfit)
- [facebook/duckling](https://github.com/facebook/duckling)
- [microsoft/Recognizers-Text](https://github.com/microsoft/Recognizers-Text)

**Data and evaluation**

- [PolyAI task-specific-datasets (BANKING77)](https://github.com/PolyAI-LDN/task-specific-datasets)
- [BANKING77 on Hugging Face](https://huggingface.co/datasets/PolyAI/banking77)
- [clinc/oos-eval](https://github.com/clinc/oos-eval)
- [jianguoz/Few-Shot-Intent-Detection](https://github.com/jianguoz/Few-Shot-Intent-Detection)
- [sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench)
- [τ-bench paper](https://arxiv.org/pdf/2406.12045)
- [Botium: testing conversational AI](https://botium-docs.readthedocs.io/en/latest/03_testing/01_testing_conversational_ai.html)
- [facebookresearch/EmpatheticDialogues](https://github.com/facebookresearch/EmpatheticDialogues)
- [unza-speech-lab/zambezi-voice](https://github.com/unza-speech-lab/zambezi-voice)
- [Zambezi Voice paper](https://arxiv.org/abs/2306.04428)

**Design research**

- [Moore and Arar: A Natural Conversation Framework for Conversational UX Design](https://link.springer.com/chapter/10.1007/978-3-319-95579-7_9)
- [The IBM natural conversation framework](https://www.tandfonline.com/doi/abs/10.1080/07370024.2022.2081571)
- [Understanding is a Two-Way Street: user-initiated repair](https://dl.acm.org/doi/10.1145/3641026)
- [NN/g: 10 guidelines for AI chatbots](https://www.nngroup.com/articles/ai-chatbots-design-guidelines/)
- [CFPB: chatbots in consumer finance](https://www.consumerfinance.gov/data-research/research-reports/chatbots-in-consumer-finance/chatbots-in-consumer-finance/)
- [awesome-conversational-ai](https://github.com/jyguyomarch/awesome-conversational-ai)
- [awesome-chatbots](https://github.com/JStumpp/awesome-chatbots)

**Checked first-hand** (PyPI, 2026-09-23): `rasa-pro` 3.20.0
(`rasa/dialogue_understanding/patterns/default_flows_for_patterns.yml`,
`commands/`), `parlant` 3.3.2 (`core/agents.py`,
`core/engines/alpha/canned_response_generator.py`), `semantic-router` 0.1.16
(`route.py`, `routers/base.py`, `encoders/`), and `dateparser` 1.4.3 (behaviour
test in §2.3).
