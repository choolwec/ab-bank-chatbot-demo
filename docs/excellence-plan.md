# The plan to make the AB Bank assistant excellent

**One plan that unifies the multi-platform, conversational and small-model research**

Written 2026-09-23 · Status: plan for approval. No application code changed.

> **Evidence base.** This plan builds on:
>
> - [`multi-platform-research.md`](multi-platform-research.md): WhatsApp,
>   Messenger and website channels, Zambian law, cost.
> - [`conversational-research.md`](conversational-research.md): repair
>   patterns, and a 15-case probe of the current bot.
> - [`../research/matcher-benchmark/`](../research/matcher-benchmark/): a
>   **measured** comparison of the current matcher against small local models.
> - The Jev and small-model research in §3 of this document.
>
> Where a number was measured in this repo, it says so. Where a figure comes
> from outside research, the source is linked in §11. **[VERIFY]** marks
> anything that must be confirmed before money or customers depend on it.

---

## 1. What "excellent" means: a measurable quality bar

"Really good" has to be something we can test, or it becomes a matter of
opinion. These are the proposed launch targets. The **baseline** column is
today's measured value where one exists.

| Area | Metric | Baseline (measured) | Launch target |
|---|---|---|---|
| **Safety** (non-negotiable) | Fraud, theft and lost-card phrasings from the red-team set that reach the fraud flow | "stole", "took money from my account" and similar are **missed** by `urgent_scan` | **100%** |
| | Everyday messages wrongly sent into the fraud or complaint flow without a confirmation question | "I didn't make it to the branch today…" opens the **fraud** flow, and "I don't want to complain, just a question" opens a **complaint** (measured) | **0** on the red-team negative set |
| | Fraud reports that include a way to reach the customer | **0% on the web.** `FraudFlow` never asks for a phone number or email, yet promises "a member of staff will contact you as a priority". (The complaint flow does ask.) | **100%** (on WhatsApp the number is usually already known; confirm it) |
| | Out-of-scope questions answered *directly* with an unrelated answer | **26.7%** of hard lookalikes (8/30) | **≤ 3%** |
| | Customer-facing text that isn't approved wording | 0% (by design) | **0%**, always |
| | Unmasked PII reaching storage or a model | 0% (tests) | **0%**, always |
| **Understanding** | In-scope questions answered correctly and directly | **53.8%** at the production threshold | **≥ 85%** direct, and **≥ 95%** direct or one-tap "did you mean" |
| | Questions answered *wrongly* and confidently | 4.4% | **≤ 2%** |
| **Conversation** | The 15-case conversational probe | **3/15** handled well | **15/15** |
| | The bot asking for something the customer already said | Happens (fraud flow) | **0** in scripted tests; tracked in production |
| | Strikes per conversation | Not yet measured | Measure the baseline in the pilot, then reduce it by at least half |
| **Access to humans** | "Talk to a person", typed *or* tapped, works in every state | Button only, inside flows | **100% of states** |
| | Handoff SLA met (callback within the promised time) | n/a | **≥ 95%** |
| **Outcome** | Self-serve rate (resolved without a ticket, and no repeat contact within 24 h) | n/a | Set from the pilot baseline |
| | CSAT (sampled, one tap) | n/a | **≥ 4.2 / 5** |
| **Channels** | Delivery failures (WhatsApp/Messenger status webhooks) | n/a | **≤ 1%** |
| | Bot messages per conversation (each is billable on WhatsApp from 1 Oct 2026) | FAQ 3, fraud report 6 (measured) | **≤ 4 average** |
| **Speed** | Our processing time per message | ~2–5 ms matching (measured) | **p95 ≤ 150 ms** server-side |
| **Inclusion** | WCAG 2.1 AA on the web | Built to spec | Keep, plus a manual NVDA and keyboard pass |

These targets are proposals. Confirm them with the product owner,
contact-centre lead and compliance in Phase 0, and put them in `admin/report.py`
so they're checked every week.

---

## 2. Principles we won't compromise

1. **Models choose; people write.** No model ever writes customer-facing text.
   Models only *decide*: which intent, which slot value, whether to answer or
   abstain. Every word a customer sees is approved wording from the YAML.
   Parlant's strict mode and Rasa's command generator show the industry doing
   the same, and the principle holds until governance explicitly says otherwise.
2. **The safety path is redundant.** Urgent topics are caught by rules *and*,
   from Tier 2, by a second model-based check. The two must agree to *skip* the
   fraud flow, but either one is enough to *enter* it.
3. **There's always a way out.** "Talk to a person" works typed or tapped, from
   any state, on every channel.
4. **Handle a conversation the way a person would.** Corrections, digressions,
   "yes", "what do you mean?" and "I already told you" are handled, never
   counted as failures.
5. **Evaluation decides what ships.** A change to content, thresholds or models
   ships only if the evaluation suite shows no regression. "Content edits are
   deploys" extends to "model edits are deploys".
6. **Data stays in Zambia.** Prefer models that run on our own server. A hosted
   AI API is used only after a legal ruling and a zero-retention contract.
7. **One brain, many channels.** A single core, with each channel rendering the
   same content in its own format.
8. **Respect the customer's time and data bundle.** Keep answers short and
   complete in the chat, send fewer messages, and never make a link the only way
   to get the answer.

---

## 3. Small models and Jev: findings

### 3.1 Jev (TypeSafe AI)

**What it is.** I read the `typesafe-sdk` 0.7.1 source from PyPI.

- Jev is a hosted "System One" model at `POST /v1/systemone`. It **doesn't
  generate text**. You send a *state* (the customer's message and context) and
  typed questions, and it returns an answer *with probabilities*.
- There are three question types:
  - `Choice`: labels with descriptions, returning the chosen label and a
    probability for each.
  - `Noul`: yes/no.
  - `Score`: an ordered rubric.
- One call can ask several questions about the same message. For us, that could
  be the intent, "is this a correction?", "is the customer frustrated?" and "is
  this urgent?" together.
- Billing is per input token (reported as $0.042 per million, with output free).
  Reported latency is 70–500 ms. It's English-first, with other languages
  handled "not equally well". It's in **early access**, launched around 17–19
  September 2026, and zero-data-retention is offered to enterprise customers.

**Independent evidence** (§11):

- With category definitions plus 24 labelled examples per call, it scored
  **92.4% on BANKING77**. A fine-tuned BERT scored 93.66%.
- In a *pre-registered* evaluation it scored **0.832**, where a supervised
  encoder scored **0.933** under the same conditions. The authors' summary:
  "where labeled data exists, a 9 ms supervised encoder wins… at no per-call
  cost, on a laptop."
- It beat a nano-class LLM on CLINC150 by 7.5 points and trailed a frontier LLM
  by 4.5.
- On the community JevBench, it scored **74.4**. **SemIf**, an MIT-licensed open
  re-implementation running on an open **Qwen3.5-4B**, scored **73.1**.

**Verdict for AB Bank:**

- **Not in the production path now.**
  - It's hosted outside Zambia, which runs into Data Protection Act s.70 and
    §3 of the multi-platform research.
  - It's a very new vendor in early access.
  - We *have* labelled data, which is exactly where a small supervised or
    embedding model wins, and runs locally at no per-call cost.
  - It's English-first.
- **Adopt its design.** Our understanding layer should work the same way:
  typed decisions, calibrated probabilities, and an explicit *abstain*. §4 does
  this with local models.
- **Keep it as an option.**
  - Re-evaluate it if TypeSafe offers in-region or self-hosted deployment with a
    signed zero-retention agreement.
  - It could serve offline as a *second opinion* on **staff-written or synthetic**
    phrase sets, where disagreements point at weak intents.
  - For a self-hosted version of the same pattern, SemIf's approach (reading
    option probabilities from an open model) can run on our own hardware in V2.

### 3.2 What we measured: current matcher against small local models

`research/matcher-benchmark/` uses 91 unseen in-scope phrasings and 30
out-of-scope questions, mostly lookalikes. Everything runs on CPU.

| System | Top-1 | At ≤10% of out-of-scope answered: right | wrong |
|---|---|---|---|
| Current matcher (TF-IDF + fuzzy) | 89.0% | 37.4% | 2.2% |
| all-MiniLM-L6-v2 embeddings (22M params) | 89.0% | 74.7% | 4.4% |
| **Hybrid rank + embedding gate** | **94.5%** | **74.7%** | **3.3%** |
| Supervised head on embeddings | 92.3% | 51.6% | 0.0% |

At today's production threshold, the current matcher **directly answers 8 of 30
out-of-scope questions**:

- "i need a lawyer" → how to apply for a loan
- "how do i open a facebook account" → account opening
- "what time does shoprite close" → our opening hours

The small model costs about **3 ms per message** on CPU. The two approaches fail
on different inputs. Character n-grams catch misspellings and embeddings catch
meaning, so combining them lifts top-1 accuracy from 89% to 94.5%. Using the
embedding score to decide *whether to answer* doubles the correct direct answers
at the same out-of-scope exposure.

*Caveat:* the set is small and self-written, so this is directional. §5 builds
the real evaluation set.

### 3.3 The small-model landscape, by job

| Job | Best candidates (2026) | Size / licence | Fit for us |
|---|---|---|---|
| **Scoring meaning and deciding when to abstain** | all-MiniLM-L6-v2 (tested), multilingual MiniLM/E5-small for code-mixing, Qwen3-Embedding-0.6B, EmbeddingGemma-300M, BGE-M3; model2vec static embeddings where speed matters most | 22M–600M. Apache-2.0 / MIT, except Gemma, which has its own terms **[VERIFY each]** | **Adopt in Tier 2.** Start with a MiniLM-class model, and test a multilingual one against code-mixed phrases. |
| **Few-shot intent classifier with an out-of-scope class** | SetFit (Apache-2.0, 1.2.0, Sep 2026) on a sentence-transformer | Small | A strong option *once* there are enough real phrases and negative examples. Compare it with the gated hybrid on the golden set. |
| **Pulling values out of messages** (dates, amounts, channel, branch, names) | **GLiNER2** (205M, Apache-2.0, pip 2.0.0 Aug 2026): named entities, classification and structured extraction in one CPU pass. dateparser as a date helper (tested: good on common forms, misses "this morning" and "last night", misreads "10am"). | Small, CPU | **Adopt for pre-filling** (conversational research §4.4), always showing the value back for confirmation and never overwriting the customer's words |
| **Typed decisions without text** | Jev (hosted); SemIf (MIT, open models such as Qwen3.5-4B) | API; 4B open model | Design pattern now. Self-hosted SemIf-style in V2. |
| **Small LLM for understanding** (V2 command generator) | Qwen3.5-4B (a leading CPU choice in 2026 round-ups), SmolLM3-3B (Apache-2.0), Phi-4-mini (MIT), Granite 4.x (Apache-2.0), Gemma 4 E2B/E4B (Gemma terms), Rasa's fine-tuned Llama-3.1-8B command generator | 2–8B; quantised to run on CPU via llama.cpp (MIT) | **V2 only**, behind a schema with constrained output. A July 2026 study of 41 open models found instruction-tuned 3B models can beat 7B base models at intent classification. |
| **Local languages** (Bemba, Nyanja, Tonga, Lozi) | Serengeti (517 African languages including Bemba; **licence [VERIFY]**); MADLAD-400 translation (Apache-2.0; quality for Bemba and Nyanja untested) | — | **No production-ready, commercially licensed option was found.** NLLB-200, Tiny Aya and the Zambezi Voice corpus are all **non-commercial**. The plan is to collect AB Bank's own phrase data (§4, workstream D). |
| **Runtime** | ONNX Runtime 1.30 (MIT); llama.cpp / llama-cpp-python (MIT) | — | CPU-only on the Lusaka VM. No GPU needed for Tiers 1–2. |

---

## 4. Target architecture: how the bot makes each decision

```
customer message (any channel)
   │
   ▼
guards.mask()  ── PII removed before anything else (unchanged invariant)
   │
   ▼
SAFETY LAYER ─ rules (urgent_scan, widened) OR model check (Tier 2)  →  fraud / complaint flow
   │            either one can trigger it; neither can suppress the other
   ▼
CONVERSATION MANAGER (Tier 1, deterministic)
   ├─ global commands ("cancel", "agent", "menu", "0")      any state, whole-message match
   ├─ expected answers (yes/no, "2", typed button label)    from session.expecting
   ├─ repair ("what do you mean?", "say that again")        answer_simple / repeat
   ├─ frustration                                            calm + human, no strike
   └─ in a flow?  classify first: correction → digression → answer
   │
   ▼
UNDERSTANDING LAYER (Tier 2, local models, deterministic output)
   ├─ rank intents:  char n-gram score  ⊕  embedding score  (+ context boost from the topic slot)
   ├─ decide:        calibrated gate on the embedding score →  answer | did-you-mean | abstain
   └─ extract slots: GLiNER2 / dateparser / regex  →  pre-fill, always confirmed
   │
   ▼
RESPONSE: approved templates only (YAML), rendered per channel (web / WhatsApp / Messenger)
   │
   ▼
audit (masked) · tickets → Jira / agent inbox · metrics
```

In **V2, after the legal ruling**, a small local LLM can sit *beside* the
understanding layer as a command generator (`StartFlow`, `SetSlot`,
`CorrectSlots`, `Clarify`, `CancelFlow`), running first in shadow mode. Its
output is validated against a schema and discarded if invalid. It never produces
text.

---

## 5. The evaluation harness: what makes "excellent" repeatable

Excellent bots aren't built in one go. They're measured and fixed every week.
This harness is what stops quality from slipping.

**Datasets** (versioned in git and reviewed like content):

1. **Golden in-scope set.** At least 30 phrasings per intent, drawn from masked
   pilot transcripts, social-media and contact-centre staff ("how do customers
   actually say this?"), and BANKING77 queries mapped to our intents (CC BY 4.0,
   commercial use allowed with attribution). It starts from
   `research/matcher-benchmark/heldout_v0.py`.
2. **Out-of-scope set** of at least 300. Generic questions, hard lookalikes (as
   in v0), and CLINC150's out-of-scope queries **[VERIFY licence]**. This is the
   set that protects the bank.
3. **Conversation scripts.** The 15 probe cases plus every bug found in review,
   written as multi-turn pytest scenarios that assert on stored slots, strikes,
   resumes and handoffs.
4. **Red-team set.** Fraud phrasings (tense variants, Zambian English,
   misspellings, "someone took…"), PII, abuse, prompt-injection-style text for
   V2, and channel-limit checks.

**Gates in CI** (pytest):

- Fraud recall is 100% on the red-team set.
- Confident wrong answers stay at or below the §1 target.
- Directly answered out-of-scope questions stay at or below target.
- No drop of more than 1 point in golden-set accuracy.
- All conversation scripts pass.

A failing gate blocks the commit, the same as the existing "no dead ends" test.

**Shadow mode.** Run any new matcher or model *beside* the live one in
production. Log where they disagree, review the disagreements weekly, and switch
only when the gates pass on real traffic.

**Human review.** Every week, two reviewers score 50 randomly sampled
conversations against a rubric: correct, safe, warm, repaired, and escalated
when it should be. Disagreements between reviewers become new test cases.

**Calibration.** Fit the thresholds on a calibration split, never on the test
set. Split conformal prediction can bound the rate of confident wrong answers,
a guarantee that's easy to explain to compliance. It's optional, but worth
having.

---

## 6. Workstreams

| # | Workstream | What "excellent" requires | Evidence |
|---|---|---|---|
| A | **Safety and trust** | Widen `urgent_scan` (stole, took, taken; eTumba versus card intro). Collect contact details in the fraud flow. Build the red-team set. Add the model-based second urgent check (Tier 2). Anti-impersonation lines and the verified WhatsApp badge. Keep PII tests as compliance controls. | Conversational research §3; multi-platform research §4 |
| B | **Conversation design** | All Tier 1 patterns. A tone and voice guide (plain English, short, warm, never blaming). Built-in texts moved to `knowledge/system_messages.yaml` so legal can review them. `answer_simple` and `short_label` on every intent. One question per message. | Conversational research §4 |
| C | **Understanding** | The golden and out-of-scope sets. The hybrid ranker with an embedding gate. An explicit out-of-scope class. Calibrated thresholds. Context carry-over. GLiNER2/dateparser pre-filling. Weekly retraining from unmatched phrases. | §3.2, §3.3 |
| D | **Content** | Cover what customers *actually* ask: mine the Social Media Response Template, contact-centre call reasons and pilot transcripts. Map BANKING77 intents to find coverage gaps. Resolve every `[CONFIRM`. Give each answer an owner and a review date. Plan Bemba and Nyanja phrase collection. | Knowledge base, BANKING77 |
| E | **Channels** | The WhatsApp and Messenger plan: renderer, webhooks, templates, costs | Multi-platform research §5–§8 |
| F | **Human handoff and operations** | An agent inbox (Chatwoot self-hosted as the target). SLAs and out-of-hours promises. The 24/7 fraud-route decision. A "bot got this wrong" button for agents, which feeds the test sets. | Multi-platform research §7.6 |
| G | **Measurement** | The §5 harness, the per-channel weekly report against the §1 targets, shadow mode, and an incident process for any safety miss | §1, §5 |
| H | **Platform and compliance** | Zambian hosting, persistent sessions, the DPIA and ODPC position, retention, model hashes pinned in deploys | Multi-platform research §3, §7.8 |
| I | **Inclusion** | WCAG on the web, low-literacy wording, a graceful voice-note reply (transcription later), code-mixed phrases | Multi-platform research §4 |

---

## 7. Roadmap

Sizes assume one developer, with a content owner and a compliance reviewer
alongside. Phases overlap, and they're gated by exit criteria rather than dates.

| Phase | Scope | Exit criteria |
|---|---|---|
| **0: Foundations** (week 0–1) | **Fix the two safety gaps:** widen `urgent_scan`, and make the fraud flow collect a contact number or email so the promised follow-up is possible. Adopt the quality bar (§1). Start evaluation harness v0: the probe cases as `xfail(strict=True)` scenarios, `heldout_v0` as a seed, and red-team additions. Record baseline metrics. Start the paperwork from the multi-platform plan (legal ruling, Meta verification, Zambian hosting). | Red-team fraud recall is 100%. The baseline report exists. Owners are named for every §10 decision. |
| **1: Conversation** (weeks 1–4) | The Tier 1 patterns (global commands, expected answers, repair, frustration, in-flow correction and digression, confirmation). System messages moved to YAML. Tone guide. Content-coverage sprint. | All 15 probe cases pass. Legal has signed off the new system messages. |
| **2: Understanding** (weeks 3–7) | Golden and out-of-scope sets built from real sources. The hybrid ranker with an embedding gate, in **shadow mode**. GLiNER2/dateparser pre-filling. Calibrated thresholds. | The §1 understanding and safety targets are met on the golden and out-of-scope sets. Two weeks of shadow logs have been reviewed. Legal has been briefed on local model use. |
| **3: Channels** (weeks 4–10) | The channel-ready core, then a WhatsApp pilot (staff first), then Messenger, following the multi-platform plan | The pilot meets the §1 channel targets, and the weekly report is broken down by channel |
| **4: Humans and polish** (weeks 8–14) | The agent inbox, the "bot got this wrong" loop, sampled CSAT, dashboards, and the first round of local-language phrases | Handoff SLA ≥ 95%, CSAT at target, self-serve baseline set |
| **5: V2** (after the legal ruling) | A small local LLM as command generator, in shadow then limited rollout. Revisit Jev or SemIf-style decisions if data residency allows it. | Beats Tier 2 on the golden, out-of-scope and conversation sets, with no safety regression |

---

## 8. What excellent looks like (illustrative wording, pending legal review)

**Fraud report on WhatsApp.** The bot uses what the customer already said,
confirms it, handles a question asked mid-report, and ends in a single ticket.

> **Customer:** someone took K500 from my etumba yesterday i didnt do it
> **Bot:** I'm sorry, that's worrying. I'm treating it as urgent. You said
> **K500** was taken from **eTumba** **yesterday**. Is that right?
> [Yes, that's right] [Something's different]
> **Customer:** yes. can they reverse it?
> **Bot:** Our fraud team will look at reversing it as part of your case. I can't
> promise the outcome, but a person will follow up with you. One more thing:
> what's the best number to reach you on?
> **Customer:** 0977 123 456
> **Bot:** Got it: 0977 123 456. Your case reference is **FRD-20260923-X7K2**.
> A member of our team will contact you as a priority. We will never ask for your
> PIN or OTP.
> [Talk to a person now] [Main menu]

That's 3 bot messages after the customer's first message, against 5 today. No
question is repeated, a question asked mid-report gets answered, and, unlike
today's fraud flow, the bank ends up with a way to reach the customer.

**A correction and a digression in the callback flow:**

> **Bot:** What phone number should we call?
> **Customer:** what time do you close on saturday?
> **Bot:** Our branches are open Saturday 09:00–12:30. Now, back to your
> callback: what number should we call?
> **Customer:** 0977123456 … sorry, it's 0966123456
> **Bot:** Thanks, I've updated it to **0966 123 456**. What would you like to
> discuss?

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Trusting a model too much | Principle 1 (models choose, never write), shadow mode, CI gates, and a redundant safety path |
| A biased evaluation set (v0 is self-written) | The golden set comes from real, masked transcripts and staff phrasings. Reviewer disagreements feed it. |
| Model drift or silent swaps | Model files pinned by hash, and "model edits are deploys" enforced through the gates |
| Licence traps | NLLB, Tiny Aya and Zambezi Voice are non-commercial. Keep a licence register and **[VERIFY]** each model before use. |
| Vendor risk (Jev is in early access) | Not in the production path. Our architecture doesn't depend on any hosted model. |
| Data residency | Local CPU models for Tiers 1–2. Any hosted model only after a legal ruling and a zero-retention agreement. |
| Team capacity | Phases are gated, not dated. Tier 1 alone fixes most visible failures. |
| Scope creep into transactions | V1 stays non-transactional. Balance and transfer requests get a clear approved redirect (eTumba `*888#`, MyABZ). |

---

## 10. Decisions needed

| # | Decision | Suggested owner |
|---|---|---|
| 1 | Adopt the §1 quality bar as launch criteria | Product owner + Compliance |
| 2 | Approve **local, non-generative** models (Tier 2) for routing decisions. This is separate from the V2 LLM ruling. | Legal / DPO |
| 3 | Access to **masked** pilot transcripts for the evaluation set, with a retention rule for that set | DPO |
| 4 | A named content owner and a legal reviewer with a fortnightly release rhythm | Management |
| 5 | Out-of-hours fraud promise and the 24/7 route | Operations / Risk |
| 6 | Everything in the multi-platform plan's §10 (hosting, WhatsApp number, handoff tool, templates) | As listed there |

---

## 11. Sources

**Jev**

- [TypeSafe: introducing System One models and Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
- [TypeSafe docs: models](https://docs.typesafe.ai/models)
- [typesafe-sdk on PyPI](https://pypi.org/project/typesafe-sdk/) (source read, v0.7.1)
- [Requesty: Jev pricing](https://www.requesty.ai/model/typesafe/jev)
- [Firecrawl: what is Jev](https://www.firecrawl.dev/blog/what-is-jev)
- [KDnuggets: what everyone is getting wrong about Jev](https://www.kdnuggets.com/what-everyone-is-getting-wrong-about-typesafe-ais-jev)
- [MarkTechPost: Jev release](https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/)
- [Forbes: why everyone is talking about Jev](https://www.forbes.com/sites/ronschmelzer/2026/09/22/why-everyone-is-talking-about-jev-the-ai-that-doesnt-chat/)
- [simonmesmith/jev-banking77-experiment](https://github.com/simonmesmith/jev-banking77-experiment)
- [ickma2311/jev-baselines-eval (pre-registered)](https://github.com/ickma2311/jev-baselines-eval)
- [dhruvmehra/jevbench](https://github.com/dhruvmehra/jevbench)
- [JevBench v1 results](https://benchmarkheaven.com/jev-models/v1)
- [adilmoujahid/jev-banking77-demo](https://github.com/adilmoujahid/jev-banking77-demo)
- [TheoLeeCJ/SemIf](https://github.com/TheoLeeCJ/Semif)
- [MindStudio: Jev vs classic classifiers](https://www.mindstudio.ai/blog/jev-vs-classic-classifiers-benchmark)

**Small models**

- [Selecting open-weight LMs for zero-shot intent classification (41 models)](https://arxiv.org/abs/2607.27421)
- [Qwen3 Embedding paper](https://arxiv.org/pdf/2506.05176)
- [BentoML: open-source embedding models 2026](https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models)
- [BentoML: small language models 2026](https://www.bentoml.com/blog/the-best-open-source-small-language-models)
- [Popular AI: best CPU-only local LLMs 2026](https://www.popularai.org/p/best-cpu-only-local-llm-2026)
- [GLiNER2 paper](https://arxiv.org/pdf/2507.18546)
- [fastino-ai/GLiNER2](https://github.com/fastino-ai/GLiNER2)
- [huggingface/setfit](https://github.com/huggingface/setfit)
- [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router)

**Local languages**

- [SERENGETI](https://github.com/UBC-NLP/serengeti)
- [AfroBench](https://mcgill-nlp.github.io/AfroBench/)
- [IrokoBench](https://aclanthology.org/2025.naacl-long.139.pdf)
- [Tiny Aya licence](https://www.therundown.ai/tools/tiny-aya)
- [NLLB vs MADLAD licensing](https://picovoice.ai/blog/open-source-translation/)
- [Zambezi Voice](https://github.com/unza-speech-lab/zambezi-voice)

**Evaluation**

- [BANKING77](https://github.com/PolyAI-LDN/task-specific-datasets)
- [CLINC150](https://github.com/clinc/oos-eval)
- [tau2-bench](https://github.com/sierra-research/tau2-bench)
- [Selective conformal risk control](https://www.arxiv.org/pdf/2512.12844)

The earlier research documents list the sources for channels, law and
conversation design.
