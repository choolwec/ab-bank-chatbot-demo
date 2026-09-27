# Voice chat with a natural, custom voice (27/09/2026)

**Question:** can the bot talk back by voice, in a voice trained on a real
person, so it sounds natural? What does Hugging Face offer for that?

**Short answer: yes, and without breaking the bot's main rule.** The voice only
*reads* the approved answer text. It never makes up words. The practical plan
is to record one hired voice actor once. That recording can then be used three
ways: played as-is, used to clone the voice, or used to train a small custom
voice. Pre-render every approved answer to audio at content-deploy time, and
send the audio *alongside* the text and buttons, never instead of them.

This builds on `huggingface-research.md` §3 (listening to voice notes, ticket
V1). Numbers below were measured on a 4-core CPU with no GPU, the same kind of
machine as the Lusaka VM. Code: `research/voice/bench_tts.py`.

---

## 1. How voice fits the bot

```
customer voice note ──► speech-to-text (V1, faster-whisper) ──► "I heard: …  Is that right?"
                                                                  │
                                                     same router.handle(), unchanged
                                                                  │
approved answer text ──► spoken version (`spoken:` in YAML) ──► voice ──► audio file
                                                                  │
       text + buttons are always sent; the audio is an extra message (or a ▶ play button on the web)
```

- **Models choose, people write** (excellence plan, principle 1) still holds:
  the voice model turns approved words into sound. It chooses nothing.
- **A voice note cannot carry buttons.** So the "no dead ends" rule is still
  met by the text message. The audio comes after it, as an extra.
- **Voice replies only to voice.** Send audio only when the customer sent a
  voice note, or tapped ▶ on the web. The bank never *starts* a conversation
  with a voice note (see §6).

---

## 2. Three ways to get "a real person's voice"

All three start from the **same recording session** with one contracted voice
actor, about 1–2 hours in a quiet room. The script is our approved answers plus
a set of varied sentences. Book it once, then decide.

| Option | How natural | Runs on our CPU? | What changes when an answer changes | Licence |
|---|---|---|---|---|
| **A. Play the recordings as they are** | Most natural: it *is* the person | Nothing to run | The actor records the new line | Contract only |
| **B. Clone the voice** from a few minutes of the recording: Chatterbox (MIT) or Qwen3-TTS 0.6B (Apache-2.0, official fine-tuning scripts) | Very close to the person | Too slow live (below); fine for **pre-rendering** at content deploy | Re-render just that line, in minutes | MIT / Apache-2.0 |
| **C. Train a small voice** (Piper) on the 1–2 hours | Good, a little flatter | **Yes, 30× faster than real time**, so it works live | Nothing: it reads any text | Engine GPL-3.0 **[VERIFY with Legal]**; our trained voice is ours |

**Recommendation: B for the approved answers, C only if live speech is ever
needed.** About a quarter of the built-in texts (52 of 200) have placeholders, and some of those are live values (names, case
references, phone read-backs, branch results). Until C exists, those stay as
text only. Keep A as the fallback if listeners prefer the real recordings for
the top 20 answers.

**Why not clone from a few seconds of someone's voice** (the "3-second
cloning" these models advertise)? Because the consent, the audio quality and
the result all matter more for a bank than speed. Use proper studio audio from
a contracted actor, never a staff member's or a customer's voice (§6).

---

## 3. What was measured (4 CPU threads, no GPU)

Real answers from `knowledge/intents/` (20–40 seconds of speech each):

| Voice | Custom voice possible? | Size | Speed (real-time factor: lower is faster) | A 20 s answer takes |
|---|---|---|---|---|
| **Piper** `en_US-lessac-medium` | Yes, by training (option C) | 63 MB | **0.03** | **0.6 s** |
| **Kokoro-82M** (Apache-2.0), fp32 ONNX | No official training code for new voices | 326 MB | 0.23 | 4.6 s |
| Kokoro-82M, int8 ONNX | — | 92 MB | 1.3 (slower on this CPU) | 27 s |
| **Chatterbox** (MIT), cloning a reference voice | Yes, cloning (option B) | ~3 GB | 3.7 | ~29 s for an 8 s reply |

**What this means:**

- Chatterbox is **too slow to answer live on CPU** but fine for pre-rendering.
  All built-in text is about 25,600 characters, roughly **25–30 minutes of
  speech**. At that speed a full re-render is about **2 hours of CPU**, run
  overnight at content deploy, and a single changed answer takes seconds to
  minutes. A GPU is not required.
- Piper is fast enough to speak **anything** live, including read-backs, on the
  existing VM.
- **Watermark check:** Chatterbox marks everything it generates with Resemble's
  Perth watermark (MIT). The detector read **1.0** on Chatterbox output and
  **0.0** on Piper output. That lets the bank prove whether a voice note came
  from its own system.

---

## 4. The answers need a spoken version first

Our answers are written for a screen. This is how the pronunciation step
(espeak-ng, used by Kokoro and Piper) reads them today:

| On screen | Read aloud as |
|---|---|
| ZMW 100 | "zee-em-double-you one hundred" |
| 08:00-15:00 | "zero eight zero zero dash fifteen zero zero" |
| *778# | "asterisk seven hundred seventy-eight hash" |
| Monday-Friday | "Mondayfriday" |
| Kitwe | "Kit-wee" |
| Tamanga | English vowels ("Tam-ANG-a") |
| NRC, TPIN, eTumba | Fine |

On top of that, bullet lists, "[CONFIRM …]" notes and 40-second answers don't
work by ear.

**Change:** an optional `spoken:` field per intent answer and system message.
It is short (aim for 15 seconds or less), written for the ear ("one hundred
kwacha", "eight in the morning to three in the afternoon", "star seven seven
eight hash"), and reviewed by Legal like any wording. Add a small
pronunciation list for place and product names ("Kitwe", "Tamanga", "Chipata")
checked by a Zambian speaker.

Tests:
- No `spoken:` text contains digits with colons, "ZMW", "[CONFIRM" or `*`.
- Every intent that has audio has a `spoken:` text.
- `admin.legal_export` prints the spoken text beside the written one.

---

## 5. Per channel

- **WhatsApp:** upload the audio (OGG/Opus) to the Graph media endpoint and send
  an `audio` message after the text+buttons message. Pre-rendered files are
  uploaded once per content version; Meta returns a media id. This adds one
  message per reply, so check it against the P5 message budget. Replies inside
  the 24-hour service window cost nothing extra **[VERIFY current pricing]**.
- **Web widget:** a ▶ button on bot bubbles that plays
  `/audio/<content-hash>.ogg`. It must be keyboard- and screen-reader-friendly
  (WCAG 2.1 AA): off by default, never autoplay. It also helps customers who
  read with difficulty.
- **Messenger:** audio attachments work the same way; lowest priority.
- **Live two-way voice** (talking to the widget like a phone call): not
  recommended yet. It needs speech-to-text at the Whisper accuracy measured in
  `huggingface-research.md` §3, plus a live voice (option C). Revisit after the
  V1 shadow review.

---

## 6. Safety, consent and law: read before recording anyone

- **A natural bank voice is exactly what fraudsters imitate.** Voice-note scams
  that pretend to be the bank are a real threat, and a familiar bank voice
  makes fake ones more believable. So:
  - Voice only in reply to a customer's voice note or ▶ tap; never an outbound
    or marketing voice note.
  - Every voice reply starts with a fixed line, e.g. "This is the AB Bank
    automated assistant." Legal writes the wording.
  - The anti-impersonation message ("we will never ask for your PIN or OTP")
    gets a spoken version too.
  - Keep the watermark on (Chatterbox) and keep a hash list of every published
    audio file, so the contact centre can check a voice note a customer
    forwards.
- **Consent.** Hire a professional voice actor under a written contract that
  covers synthetic use, the channels, how long it runs, and what happens to the
  model when it ends. **Never** clone a staff member (it gets awkward when they
  leave, and it invites impersonation), and **never** a customer.
- **Data protection.** Zambia's Data Protection Act 2021 treats biometric data
  (physical or behavioural characteristics that uniquely identify a person) as
  **sensitive personal data**. A voice model trained on one person is very
  likely in scope. Add it to `dpia-draft.md`, keep the raw recordings encrypted
  on the Lusaka server, and let the ODPC position (L-tickets) decide
  **[VERIFY with Legal / DPO]**.
- **Industry signal:** Microsoft restricted its VibeVoice model to research use
  because of deepfake misuse. Treat voice cloning as a controlled asset, not a
  toy.

---

## 7. Local languages by voice

- **Bemba, Nyanja, Tonga, Lozi: no usable ready-made voice.** Meta's MMS voices
  for Bemba (`mms-tts-bem`) and Nyanja (`mms-tts-nya`) are **non-commercial**.
  The Chichewa Open Bible voices (`multilingual-tts/*-OpenBible-Chichewa`,
  CC BY-SA 4.0) are Malawian Bible reading, not a bank's voice. Chatterbox and
  VoxCPM2 support Swahili, but none of our languages.
- **The realistic path is option A**: record a Bemba or Nyanja voice actor
  reading the approved spoken answers once those answers exist in that language
  (see the language plan: understand first, reply later). Option C (training
  Piper on those recordings) depends on espeak-ng pronunciation support for
  Bemba **[VERIFY]**.

---

## 8. Licences

**Usable (commercial use allowed), re-check before download [VERIFY]:**

| Model | Licence | Note |
|---|---|---|
| `ResembleAI/chatterbox` (English and Multilingual V3) | MIT | Cloning; watermark built in |
| `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | Apache-2.0 | Cloning; official single-speaker fine-tuning |
| `hexgrad/Kokoro-82M` | Apache-2.0 | Fast, fixed voices |
| `openbmb/VoxCPM2` | Apache-2.0 | 2B, needs a GPU for speed |
| `neuphonic/neutts-air` | Apache-2.0 | On-device cloning, not tested here |
| `OpenMOSS-Team/MOSS-TTS-Nano-100M` | Apache-2.0 | 0.1B, CPU; not tested here |
| Piper (`OHF-Voice/piper1-gpl`) | GPL-3.0 engine | Run as a separate process; each voice has its own licence |

**Traps (not for a bank without a separate licence):**

| Model | Licence |
|---|---|
| `coqui/XTTS-v2` | Coqui Public Model Licence (non-commercial) |
| `SWivid/F5-TTS`, `E2-TTS` | CC BY-NC 4.0 |
| `k2-fsa/OmniVoice` (600+ languages) | Code Apache-2.0, **weights CC BY-NC** |
| `fishaudio/*`, `SparkAudio/Spark-TTS-0.5B` | CC BY-NC-SA 4.0 or custom |
| `mistralai/Voxtral-4B-TTS-2603` | CC BY-NC 4.0 |
| `facebook/mms-tts-*` (including Bemba and Nyanja) | CC BY-NC 4.0 |
| `microsoft/VibeVoice-*` | MIT, but "research purposes only" in the card |
| `bosonai/higgs-*`, `IndexTeam/IndexTTS-*` | Custom licences |

---

## 9. Proposed tickets

- **V2 · Spoken answers and pre-rendered voice replies.** Add `spoken:` text
  (§4) and an `admin.render_audio` script that renders every spoken text to
  OGG/Opus with a pinned model and a content hash, skipping unchanged lines. It
  also logs the watermark check. WhatsApp sends audio after the text only when
  the customer's message was a voice note; the web gets a ▶ button. Kill switch
  `VOICE_REPLIES_ENABLED` (off). **Size:** M. **Depends on:** V1 shadow review,
  Legal on §6.
- **V3 · The bank's voice.** Hire a voice actor with a synthetic-use contract,
  record 1–2 hours, then build three candidates: the raw recordings, a
  Chatterbox clone, and a Piper voice. Run a blind listening test with
  contact-centre staff and a few customers. **Owner:** Marketing + Legal, with
  engineering support. **Size:** S (engineering) plus the recording.

---

## 10. Sources

- Hugging Face model pages, licences read through the Hub API on 27/09/2026:
  [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M),
  [Chatterbox](https://huggingface.co/ResembleAI/chatterbox),
  [Qwen3-TTS 0.6B Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base),
  [VoxCPM2](https://huggingface.co/openbmb/VoxCPM2),
  [NeuTTS Air](https://huggingface.co/neuphonic/neutts-air),
  [MOSS-TTS-Nano](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-Nano-100M),
  [OmniVoice](https://huggingface.co/k2-fsa/OmniVoice),
  [XTTS-v2](https://huggingface.co/coqui/XTTS-v2),
  [F5-TTS](https://huggingface.co/SWivid/F5-TTS),
  [VibeVoice-1.5B](https://huggingface.co/microsoft/VibeVoice-1.5B),
  [mms-tts-bem](https://huggingface.co/facebook/mms-tts-bem),
  [mms-tts-nya](https://huggingface.co/facebook/mms-tts-nya),
  [VITS Open Bible Chichewa](https://huggingface.co/multilingual-tts/VITS-OpenBible-Chichewa),
  [Piper voices](https://huggingface.co/rhasspy/piper-voices)
- [Qwen3-TTS fine-tuning scripts](https://github.com/QwenLM/Qwen3-TTS/tree/main/finetuning)
- [piper1-gpl: training new voices](https://thedocs.io/piper1-gpl/usage/training/) and [Piper licensing history](https://www.cekura.ai/discover/piper-tts)
- [Resemble Perth watermarker](https://github.com/resemble-ai/perth)
- [Zambia Data Protection Act, 2021](https://zambialii.org/akn/zm/act/2021/3/eng@2021-03-24) (definitions of biometric and sensitive personal data)
