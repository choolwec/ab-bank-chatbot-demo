# Hugging Face and open-model research (27/09/2026)

**What else from Hugging Face and similar sources could make the bot better?**

This follows `excellence-plan.md` §3 (small models, Jev) and does not repeat it.
That plan already chose all-MiniLM-L6-v2 (now N3, shadow mode), lists SetFit,
GLiNER2, multilingual E5 and small LLMs for V2, and records that NLLB, Tiny
Aya and Zambezi Voice are non-commercial. This document adds what is **new**:
a measured local-language check, voice notes, evaluation data whose licence
is now confirmed, and a second PII check for staff exports.

Every licence below was read from the model or dataset page on 27/09/2026.
Licences change, so re-check each one **[VERIFY]** before download into
production, and add it to the licence register (excellence plan §6).

---

## 1. Summary: what to do, in order

| # | Change | Why | Cost | Ticket |
|---|---|---|---|---|
| 1 | **Detect Bemba, Nyanja, Tonga and Lozi messages** and answer honestly ("I understand English best for now…" + buttons + talk to a person) instead of guessing. | Measured: **53%** of real Nyanja/English chat messages get a "did you mean…?" guess today. A 1.5 MB scikit-learn model catches most of them with **0.3%** false flags on our English phrases. No new dependency. | S (2 days) | new **LG1** |
| 2 | **Add CLINC150's out-of-scope queries to `tests/eval/oos.yaml`.** | N2 was waiting on the licence. It is **CC BY 3.0**: commercial use allowed with attribution. | XS | N2 |
| 3 | **Use InjongoIntent (Apache-2.0) as the template for the Bemba/Nyanja phrase workshop**, and its English split as extra test phrasings. | It is the first African multilingual intent set (16 languages, built from CLINC by native speakers who *culturally adapt*, not just translate). It includes balance, bill and transfer intents. No Zambian language, so our own collection is still needed. | XS | N1, N8 |
| 4 | **Transcribe English voice notes in shadow mode** with faster-whisper (MIT) on our own server; keep sending `voice_not_supported` until the numbers are reviewed. | Voice notes are common on WhatsApp in the region (multi-platform research §4). Whisper is weak on African-accented English (see §3), so measure before promising anything. | M (3–4 days + review) | W5 extension, new **V1** |
| 5 | **Second PII pass on staff exports** (`admin.export_bot_wrong`, the weekly report's unmatched list) with GLiNER-PII (Apache-2.0) or Presidio (MIT). | `guards.mask()` catches cards, NRCs, accounts and PINs; names, addresses and e-mails in free text are only caught by `looks_personal()`'s regex. Offline only, so no live latency. | S (1–2 days) | H4 follow-up |
| 6 | **Feed real code-switched Nyanja/English chat into N8** (Chichewa–English code-switch set, Apache-2.0) as negative and language-ID test material. | `tests/eval/code_mixed.yaml` has 8 unverified seed items. This is 247 real code-switched chat lines. It is Malawian Chichewa, close to Zambian Nyanja but not the same: a speaker must check it. | XS | N8 |

Not recommended now: an LLM, a translation model in the live path, Bemba/Nyanja
speech recognition, a toxicity model (see §7 and §8).

---

## 2. Local-language detection (measured)

**The problem.** `smalltalk.yaml` recognises a few greetings ("muli bwanji",
"mulishani", "zikomo", "natotela"). Anything else in Bemba or Nyanja goes to the
character matcher, which guesses. On 247 real Nyanja/English code-switched chat
lines the current matcher (production thresholds) gives:

- **12 direct answers.** Most are right ("Ndikufuna to talk to agent" →
  `human_handoff`), one is wrong: "Business ili bwino" ("business is going
  well") gets the **SME loan** answer.
- **130 "did you mean…?" suggestions (53%).** Almost none relate to the
  message. Each one costs the customer a turn, and a suggestion is not a
  strike, so a customer who keeps writing in Nyanja can get suggestion after
  suggestion and never reach the two-strike handoff.
- 105 fallbacks.

**What was tested.** `research/language-id/bench_lid.py` trains a TF-IDF
character n-gram + logistic regression classifier (scikit-learn, already a
dependency) on 800 sentences each of English, Bemba and Nyanja (SIB-200 /
Flores-200) and Tonga and Lozi (MT560). Brand, product and town names are
blanked first, because "eTumba" and "Kitwe" read as Bantu. Full numbers are in
`research/language-id/README.md`.

| Rule | English phrases wrongly flagged (1,059) | Nyanja/English chat flagged | Short Bemba flagged |
|---|---|---|---|
| P(not English) ≥ 0.7, 3+ words | **3 (0.3%)** | 50.6% | 91.3% |

It would replace **63 of the 130** nonsense "did you mean" guesses. The Nyanja
lines it misses are mostly English-dominant ("Let us meet later"), which the
matcher can reasonably try.

**Proposed ticket LG1 · Answer local-language messages honestly.**

- Run the classifier only where the matcher would say "did you mean" or fall
  back. Never on a direct answer, a flow step, a button tap, or before the
  urgent scan: the urgent scan always runs first, so a fraud report in any
  language keeps today's path.
- Reply with a new `language_fallback` system message (draft, for Legal and
  the voice-and-tone owner): English first, one short line in the detected
  language **written by a native speaker**, and the main menu plus "Talk to a
  person". It counts as a strike, like an unmatched message, so a second one
  leads to the usual two-strike handoff.
- Log `action=language_detected` with the language code only. The weekly
  report gets one line, "unmatched messages by language", which is the
  evidence for (or against) building Bemba/Nyanja content.
- Kill switch `LANGUAGE_ID_ENABLED`, default off until a shadow week.
- Ship the model as a pickled pipeline built by an `admin.train_lid` script
  from pinned dataset revisions, hashed like the embedding model.
- **Tests:** our English phrases and held-out sets flagged ≤ 0.5% (a gate);
  the Nyanja set; "yaka pa tumba" and every seed in `code_mixed.yaml` still
  reach their intents; a fraud report in Nyanja still starts the fraud flow.
- **Licence note:** SIB-200/Flores-200 is CC BY-SA 4.0. Whether a classifier
  trained on it is a share-alike "adaptation" is a legal question
  **[VERIFY with Legal]**. The fallback is to train on MT560 (CC BY 4.0) plus
  our own collected phrases only.

**Bigger options, for offline use:** GlotLID (`cis-lmu/glotlid`, Apache-2.0
with notices) covers all seven official Zambian languages (Bemba, Nyanja,
Tonga, Lozi, Kaonde, Lunda, Luvale) plus Tumbuka, but is 1.7 GB and needs
`fasttext`. It is a good tool for labelling the weekly unmatched log, not for
the live path. ZambiaSocialBERT (Apache-2.0) separates English, Bemba, Nyanja
and Lusaka slang, but was trained on synthetic text and is about 700 MB.

---

## 3. Voice notes

Today every voice note gets `voice_not_supported` ("I can't listen to voice
notes yet…"), per W5.

**English speech recognition, on our own server:**

| Model | Licence | Size | Notes |
|---|---|---|---|
| faster-whisper `small` (CTranslate2, int8) | MIT | 484 MB | About 8 s of CPU time per minute of audio (published benchmark, 8 threads). |
| faster-whisper `base` | MIT | 145 MB | Faster, less accurate. |
| `faster-distil-whisper-small.en` | MIT | ~330 MB | English only; faster than `small`. |
| NVIDIA Parakeet TDT 0.6B v3 | CC BY 4.0 | 0.6B | Strong English ASR; needs NeMo, heavier to run. |

**The catch: accent.** AfriSpeech-MultiBench (Nov 2025) reports Whisper-large-v3
at about **21% word error rate** averaged over African accents, above 70% on
name-rich speech, and 12–18% on Kenyan and Ugandan English. No Zambian figure
was found. So a transcript is a *guess*, and numbers and names in it are the
least reliable part.

**Proposed ticket V1 · Voice notes in shadow mode, then confirm-before-act.**

1. **Shadow:** behind `VOICE_TRANSCRIBE_ENABLED` (off), transcribe in the
   WhatsApp worker, run `guards.mask()` on the text, log the masked transcript
   and what the matcher *would* have done, and still send
   `voice_not_supported`. Delete the audio as soon as it is transcribed; never
   store it.
2. **Review** a few weeks of masked transcripts with the contact centre, the
   same way as N4's shadow review.
3. **Only then** answer: "I heard: *…where is the Kitwe branch?* Is that
   right?" [Yes] [No, I'll type it], using C3's typed yes/no. A hard urgent
   signal in a transcript goes straight to a person, never through the
   confirmation. Digits heard in a voice note are never used as a phone or
   account number.
4. **DPIA:** a voice recording is personal data and can identify a person.
   Add it to `dpia-draft.md` before step 1 **[VERIFY with Legal / DPO]**.

**Bemba and Nyanja speech: not yet.** Models exist on Hugging Face, but none is
ready for a bank:

- Nyanja/Chichewa: `CLEAR-Global/w2v-bert-2.0-chichewa_34_307h` (MIT,
  38.6% WER, training-data licence unclear), `dmatekenya/whisper-*-chichewa`
  (Apache-2.0, Malawian data), `unza/xls-r-300m-nyanja-fullset` (Apache-2.0,
  2022).
- Bemba: most fine-tunes are on BembaSpeech or Meta MMS (**CC BY-NC**), or have
  no licence at all (`AbelZimba/whisper-bemba-stt` has 500k+ downloads and a
  blank model card).
- Data: `buumba641/Zambia-MultiLingual-ASR-Dataset` (CC BY 4.0, Bemba, Nyanja,
  Tonga) is growing but under 1,000 clips.

Revisit after the English shadow review.

---

## 4. Evaluation data (licences confirmed)

| Dataset | Licence | Use it for | Don't |
|---|---|---|---|
| **CLINC150** (`clinc/clinc_oos`) | **CC BY 3.0** (checked on the GitHub LICENSE and the Hub) | N2: add its 1,200 out-of-scope queries to `oos.yaml` with an attribution line. This resolves the excellence plan's [VERIFY licence]. | Copy into `phrases:`. |
| **InjongoIntent** (`masakhane/InjongoIntent`) | Apache-2.0 | Its English split (culturally adapted by African annotators) as extra held-out phrasings for banking-like intents; its method (native speakers adapt, not translate) as the brief for the N1/N8 workshop. | Expect Bemba or Nyanja: it has neither. |
| **BANKING77** (`PolyAI/banking77`) | CC BY 4.0 | Already in `tests/eval/banking77.yaml`; licence re-confirmed. | — |
| **Chichewa–English code-switch** (`suru8-ai/chichewa_english_code_switch_dataset`) | Apache-2.0 | N8 and LG1: real code-switched chat lines (247, with audio). | Treat it as Zambian Nyanja without a speaker's check. |
| **SIB-200 / Flores+** (`Davlan/sib200`, `openlanguagedata/flores_plus`) | CC BY-SA 4.0 | Language-ID training (bem, nya); test sentences. | Assume share-alike doesn't apply **[VERIFY]**. |
| **MT560 pairs** (English–Tonga, English–Lozi) | CC BY 4.0 | Language-ID training for Tonga and Lozi. | Use as chat-like text: much of it is religious. |
| **Bitext retail banking** | CDLA-Sharing 1.0 | A checklist for missing banking intents (26 intents, 9 categories). | Train on it: it is synthetic, and CDLA-Sharing is share-alike. |

---

## 5. A second PII check for staff-facing exports

The live path stays as it is: `guards.mask()` is deterministic, tested and
fast. The gap is **text that leaves the bot for people to read**:
`admin.export_bot_wrong` → `data/utterances.csv`, and the unmatched list in the
weekly report and dashboard. They rely on `looks_personal()` (masking findings
plus a regex).

- **GLiNER-PII** (`knowledgator/gliner-pii-base-v1.0`, Apache-2.0, 664 MB;
  `urchade/gliner_multi_pii-v1`, Apache-2.0): zero-shot entity extraction for
  names, addresses, e-mails, dates of birth. Needs PyTorch, so run it only in
  the admin scripts, never in the app process.
- **Microsoft Presidio** (MIT): a rule-plus-model framework; can use GLiNER as
  a recogniser.

**Change:** in `looks_personal()`, when an optional model is installed, also
withhold any line where it finds a person name or address. Missing model means
today's behaviour. Test on the masked unmatched log before switching on. Zambian
names are a known weak spot of models trained on Western data, so measure
recall on a list of common Zambian names first.

`ai4privacy/pii-masking-400k` looks useful but has a custom licence; don't use
it without Legal.

---

## 6. Embeddings: no change until N8 has data

- `intfloat/multilingual-e5-small` (**MIT**, 118M): the N8 comparison
  candidate. Licence now confirmed.
- `minishlab/potion-multilingual-128M` (MIT, static embeddings): very fast, but
  512 MB and weaker than MiniLM on meaning. Not needed at our traffic.
- `google/embeddinggemma-300m`: Gemma terms, not Apache/MIT. Needs Legal.
- Rerankers such as `BAAI/bge-reranker-v2-m3` (Apache-2.0, 568M) are too heavy
  for ~60 intents; the gated hybrid already ranks well.

The one action is N8 as written, once real code-mixed phrases exist.

---

## 7. Looked at, not recommended

- **A toxicity model** (`unitary/multilingual-toxic-xlm-roberta`, Apache-2.0):
  C5's phrase list and `ABUSE_RE` cover what the bot acts on, and a model
  trained on internet comments would misread banking complaints ("they stole my
  money") as toxic. `textdetox` models use OpenRAIL++, which adds use
  restrictions.
- **Translation in the live path** (NLLB, MADLAD-400): NLLB is non-commercial;
  MADLAD is Apache-2.0 but untested for Bemba and Nyanja, and a mistranslated
  fraud report is worse than an honest "please type in English or talk to a
  person".
- **The Bemba-English emotions corpus** (MIT): machine-labelled from English
  translations and noisy (code fragments and English mixed in). Fine as rough
  language-ID test text only.
- **An LLM**: unchanged from the excellence plan, V2 only.

---

## 8. Licence traps found in this round

| Resource | Licence | Why it matters |
|---|---|---|
| `facebook/mms-1b-all` and fine-tunes on it (many Bemba ASR models) | CC BY-NC 4.0 | Non-commercial: a bank can't use it. |
| AfriSpeech-200 | CC BY-NC-SA 4.0 | Non-commercial. Use its **published results**, not its data. |
| `CLEAR-Global/Chichewa-Synthetic-ASR-Dataset` | CC BY-NC 4.0 | Non-commercial. |
| `Wana1708/nllb-bemba-education` | CC BY-NC 4.0 | Non-commercial (and NLLB-based). |
| `AbelZimba/whisper-bemba-stt`, most `buumba641/*` models, `UBC-NLP/serengeti` | none stated | No licence means no right to use. |
| `ai4privacy/pii-masking-400k` | custom | Needs Legal. |
| `textdetox/*` | OpenRAIL++ | Use restrictions. |
| `google/embeddinggemma-300m` | Gemma terms | Not a standard open licence. |

---

## 9. Sources

Hugging Face pages (licence, size and downloads read through the Hub API,
27/09/2026):

- [cis-lmu/glotlid](https://huggingface.co/cis-lmu/glotlid) and its [language list](https://github.com/cisnlp/GlotLID/blob/main/languages-v3.md)
- [kelvinmbewe/ZambiaSocialBERT](https://huggingface.co/kelvinmbewe/ZambiaSocialBERT)
- [Davlan/sib200](https://huggingface.co/datasets/Davlan/sib200), [openlanguagedata/flores_plus](https://huggingface.co/datasets/openlanguagedata/flores_plus)
- [michsethowusu/english-lozi_sentence-pairs_mt560](https://huggingface.co/datasets/michsethowusu/english-lozi_sentence-pairs_mt560), [english-tonga](https://huggingface.co/datasets/michsethowusu/english-tonga_sentence-pairs_mt560)
- [suru8-ai/chichewa_english_code_switch_dataset](https://huggingface.co/datasets/suru8-ai/chichewa_english_code_switch_dataset)
- [michsethowusu/bemba-english-emotions-corpus](https://huggingface.co/datasets/michsethowusu/bemba-english-emotions-corpus)
- [clinc/clinc_oos](https://huggingface.co/datasets/clinc/clinc_oos) and [clinc/oos-eval LICENSE](https://github.com/clinc/oos-eval/blob/master/LICENSE)
- [masakhane/InjongoIntent](https://huggingface.co/datasets/masakhane/InjongoIntent)
- [PolyAI/banking77](https://huggingface.co/datasets/PolyAI/banking77), [bitext retail banking](https://huggingface.co/datasets/bitext/Bitext-retail-banking-llm-chatbot-training-dataset)
- [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small), [Systran/faster-distil-whisper-small.en](https://huggingface.co/Systran/faster-distil-whisper-small.en), [nvidia/parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- [CLEAR-Global/w2v-bert-2.0-chichewa_34_307h](https://huggingface.co/CLEAR-Global/w2v-bert-2.0-chichewa_34_307h), [dmatekenya/whisper-small-chichewa-2h](https://huggingface.co/dmatekenya/whisper-small-chichewa-2h), [unza/xls-r-300m-nyanja-fullset](https://huggingface.co/unza/xls-r-300m-nyanja-fullset)
- [buumba641/Zambia-MultiLingual-ASR-Dataset](https://huggingface.co/datasets/buumba641/Zambia-MultiLingual-ASR-Dataset), [facebook/mms-1b-all](https://huggingface.co/facebook/mms-1b-all), [intronhealth/afrispeech-200](https://huggingface.co/datasets/intronhealth/afrispeech-200)
- [knowledgator/gliner-pii-base-v1.0](https://huggingface.co/knowledgator/gliner-pii-base-v1.0), [urchade/gliner_multi_pii-v1](https://huggingface.co/urchade/gliner_multi_pii-v1), [ai4privacy/pii-masking-400k](https://huggingface.co/datasets/ai4privacy/pii-masking-400k)
- [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), [minishlab/potion-multilingual-128M](https://huggingface.co/minishlab/potion-multilingual-128M), [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m), [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)
- [unitary/multilingual-toxic-xlm-roberta](https://huggingface.co/unitary/multilingual-toxic-xlm-roberta)

Other sources:

- [AfriSpeech-MultiBench: African-accented English ASR (arXiv 2511.14255)](https://arxiv.org/html/2511.14255)
- [AfriSwitch: African code-switched speech recognition (arXiv 2608.26434)](https://arxiv.org/html/2608.26434): no Zambian language included
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and [a 2026 CPU comparison](https://codersera.com/blog/faster-whisper-vs-whisper-cpp-speech-to-text-2026/)
- [Microsoft Presidio](https://github.com/microsoft/presidio)
