# Research summary: open models for a better bot (27/09/2026)

For the product owner. One round of research, four questions, all tested on a
4-core CPU with no GPU (the same kind of machine as the planned Lusaka VM).
Nothing here changes the live bot. Every model runs on our own server; no
customer text goes to an outside AI service.

| Question | Short answer | Detail |
|---|---|---|
| 1. What on Hugging Face could make the bot better? | A cheap local-language check, voice notes in shadow mode, confirmed test data, a PII second pass | `huggingface-research.md` |
| 2. Which Zambian languages could we add? | Bemba and Nyanja first, through collected phrases; Tonga and Lozi detected only | §2 below |
| 3. Can the bot reply by voice, in a real person's voice? | Yes: one voice actor, answers pre-rendered, text and buttons always sent too | `voice-chat-research.md` |
| 4. Can it hold a full conversation with a local model? | Yes: Gemma 4 E2B stayed inside approved answers in every test, about 7 s a reply | `local-conversation-research.md` |

---

## 1. Hugging Face findings

- **Local-language messages are handled badly today.** Of 247 real
  Nyanja/English chat lines, the current matcher gives **53%** a "did you
  mean…?" guess unrelated to the message, and one wrong answer ("Business ili
  bwino", "business is going well", got the SME loan answer).
  A 1.5 MB scikit-learn classifier (no new dependency) flags Bemba/Nyanja with
  **0.3%** false flags on our English phrases and would replace 63 of those
  130 guesses with an honest reply. Proposed ticket **LG1**.
- **CLINC150's licence is CC BY 3.0**, so ticket N2 can add its 1,200
  out-of-scope questions (with attribution). **InjongoIntent** (Apache-2.0) is
  a model for the phrase workshop.
- **Voice notes**: faster-whisper (MIT) can transcribe English locally, but
  Whisper-class models get about 21% of words wrong on African-accented
  English, so this is shadow mode only at first. Proposed ticket **V1**.
- **Staff exports** could get a second PII pass (GLiNER-PII or Presidio),
  offline only.
- **Licence traps:** many popular African-language models and datasets are
  non-commercial (Meta MMS, NLLB, AfriSpeech, Zambezi Voice) or have no
  licence at all.

Code: `research/language-id/`.

## 2. Zambian languages

| Level | Bemba | Nyanja | Tonga | Lozi | Kaonde, Lunda, Luvale |
|---|---|---|---|---|---|
| **Notice the language** and reply honestly | Tested: 91% of short sentences | Tested: about half of mixed chat | Built in, not tested on chat | Built in, not tested on chat | Only with a 1.7 GB model (GlotLID), offline |
| **Understand questions** | Yes, with native-speaker phrases | Yes, with native-speaker phrases | Possible, less demand | Possible, less demand | Not worth it yet |
| **Reply in the language** | Needs translated answers signed off by Legal | Same | Same | Same | No |
| **Voice** | No usable model (non-commercial or unlicensed) | Best found ~39% word errors (Malawian Chichewa) | No | No | No |

- No commercially licensed translation or language model handles Bemba or
  Nyanja well enough. Understanding them is **content work**: collect 20–30
  real phrasings per common intent (including code-mixed ones like "ndalama
  zanga pa etumba") into the intent YAML, the way "muli bwanji" and "zikomo"
  already work.
- A local LLM is not the answer either: in testing, Qwen3.5 4B replied in
  **made-up Nyanja**.
- **Order:** (1) LG1 to detect and log languages; (2) if the logs justify it,
  collect Bemba and Nyanja phrases and understand them while still replying
  in English; (3) translated replies for whichever language shows most demand.

## 3. Voice replies in a custom voice

- **Measured on CPU:** Piper reads a 20-second answer in **0.6 s**; Kokoro in
  4.6 s. Chatterbox (MIT) can clone a voice but takes about 29 s for an
  8-second reply, which is fine for **pre-rendering** (all our text is about
  25–30 minutes of speech, roughly 2 hours of CPU to render).
- **Plan:** hire one voice actor under a synthetic-use contract and record 1–2
  hours. That recording can be played as-is, used to clone the voice, or used
  to train a Piper voice. Pre-render every approved answer; send audio only in
  reply to a voice note (or a ▶ tap on the web), after the text and buttons.
- **Answers need a spoken version:** "ZMW 100" is read "zee-em-double-you",
  and "08:00-15:00" as "zero eight zero zero dash…".
- **Risks:** fraudsters imitate bank voices, so use a watermark (Chatterbox
  has one; checked), a fixed "automated assistant" opening line, and never a
  staff member's or customer's voice. The DPA 2021 treats biometric data as
  sensitive. Legal decision **L10**; tickets **V2, V3**.

Code: `research/voice/`.

## 4. Full conversation with a local model

Five open models, each given only the approved answers the matcher retrieved,
across 13 turns:

| Model | Reply time | Verdict |
|---|---|---|
| **Gemma 4 E2B** (Apache-2.0) | **~7 s** | **Recommended:** accurate throughout, declined all 4 questions it should, ignored a prompt-injection attack |
| Gemma 4 E4B | ~13 s | Accurate, twice as slow |
| Qwen3.5 2B | ~7 s | Good, sloppy wording |
| Qwen3.5 4B | ~14 s | Said "about 16%" (approved: 9.3–16%); made-up Nyanja |
| Granite 4.2 3B | ~10 s | Printed its hidden rules; rejected |

- **Local voice conversation works:** spoken question → Gemma listens → the
  existing `guards.mask()` and urgent scan → grounded answer → Piper speaks,
  in **7–9 s**. A spoken "someone stole my card" was stopped by the urgent
  scan and never reached the model.
- **Capacity is the limit:** about 8 replies a minute on CPU against about 95
  messages a minute for the WhatsApp worker. So the model handles only the
  messages the current bot is unsure about, on its own VM, with a timeout back
  to today's reply.
- **Safe first version:** the approved answer is sent **word for word**, and
  the model adds at most one linking sentence. A number check alone missed
  the "about 16%" problem.
- Letting a model write customer-facing sentences changes the excellence
  plan's principle 1: Legal decision **L9**. Tickets **G1** (shadow), **G2**
  (live, web first), **G3** (voice).

Code: `research/llm-conversation/`.

---

## Proposed tickets (added to `execution-plan.md` Appendix A as *Proposed*)

| ID | What | Days | Depends on |
|---|---|---|---|
| LG1 | Detect local languages and answer honestly | 2 | Native-speaker wording |
| V1 | Voice notes transcribed in shadow mode | 3.5 | W5, L10 |
| V2 | Spoken answers and pre-rendered voice replies | 4 | V1, L10 |
| V3 | The bank's voice: recording and listening test | 1 (+ recording) | L10 |
| G1 | Local conversation model in shadow mode | 4 | — |
| G2 | Verbatim-facts conversational replies, web first | 4 | G1, L9 |
| G3 | Local voice turn | 3 | G2, V1 |

## Decisions needed

| ID | Decision | Owner |
|---|---|---|
| L9 | May a local model write customer-facing sentences (starting with verbatim facts plus one linking sentence)? | Legal / DPO |
| L10 | Voice recordings, a voice actor's synthetic-use contract, biometric data | Legal / DPO + Marketing |
| — | Is training a language classifier on CC BY-SA text (Flores-200) a share-alike adaptation? | Legal |
| — | A dedicated VM (or GPU) for the conversation model | IT |
| — | Who reviews the shadow logs each week | Contact centre |

## Reproducing the numbers

Each `research/*/` folder has a README and a script. Models and datasets are
downloaded by hand or cached in git-ignored folders and never committed. The
exact commands used are at the top of each script.
