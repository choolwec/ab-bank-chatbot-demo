# Language-ID benchmark: spotting Bemba, Nyanja, Tonga and Lozi

This is research code, not part of the app or its test suite. It asks one
question: **can the bot tell, cheaply and on our own server, that a message is
not in English?** Today a Bemba or Nyanja message either falls back or, worse,
gets a "did you mean…?" guess that has nothing to do with what was asked.

`bench_lid.py` trains a character n-gram classifier with scikit-learn (already
an app dependency, so no new package) on openly licensed text, and measures it
on short chat messages. Data comes from the Hugging Face datasets-server API
into `.cache/` (git-ignored, never committed). See the script docstring for
each dataset and its licence.

```
python research/language-id/bench_lid.py
```

## Results (2026-09-27, CPU, one process)

Trained on 4,000 sentences (800 each of English, Bemba, Nyanja, Tonga, Lozi)
in about 2 s. The model is 1.5 MB and takes about 0.03 ms per message.
Brand, product and town names ("eTumba", "Yaka", "Kitwe") are blanked before
classifying, because they read as Bantu to a character model; without that
step, 20 English phrases were flagged instead of 3.

| Flag when P(not English) ≥ | Min words | English wrongly flagged (1,059 of our phrases) | Nyanja/English chat flagged (247) | Short Bemba flagged (300) |
|---|---|---|---|---|
| 0.5 | 1 | 10.9% | 81.4% | 97.3% |
| 0.5 | 3 | 4.2% | 62.8% | 97.3% |
| **0.7** | **3** | **0.3% (3)** | **50.6%** | **91.3%** |
| 0.9 | 3 | 0.1% (1) | 19.0% | 63.7% |

The three English phrases flagged at 0.7 are "yaka pa tumba" (itself
code-mixed), "ab bank mobile money" and "change my pin".

**What the current matcher does with the same messages** (character mode,
production thresholds):

| Set | Direct answer | Did you mean | Fallback | Did-you-means the 0.7 / 3-word rule would replace |
|---|---|---|---|---|
| Nyanja/English chat (247) | 12 | **130 (53%)** | 105 | 63 of 130 |
| Short Bemba (300) | 1 | 12 | 287 | 10 of 12 |

Most direct answers are right ("Ndikufuna to talk to agent" goes to
`human_handoff`), which is why the rule should leave direct answers alone. One
is wrong: "Business ili bwino" ("business is going well") gets the SME loan
answer.

## How to read this

- **Nyanja recall looks low because the set is code-switched.** Many of its
  rows are mostly English ("Let us meet later", "Call wa taxi please"), and
  those should *not* be flagged: the matcher can try them.
- **The Bemba set is noisy.** The emotions corpus has English and code
  fragments mixed in ("Import icons via filesharing."), so 91% is a lower
  bound.
- **The English false-positive rate is measured on phrases the matcher mostly
  answers already.** In the proposed design the check only runs where the
  matcher would say "did you mean" or fall back, so a false positive costs a
  slightly different fallback message, not a wrong answer.
- Training text is formal (Flores-200 news and wiki; MT560 is largely
  religious text). Real Zambian chat will differ. Collect AB Bank's own
  phrases (workstream D) and re-run before relying on these numbers.

## Other options looked at

- **GlotLID** (`cis-lmu/glotlid`, Apache-2.0 plus notices, fastText): covers
  all seven official Zambian languages (bem, nya, toi, loz, kqn, lun, lue)
  plus Tumbuka, but the model file is 1.7 GB and needs the `fasttext` package.
  Too big for the live path; a good offline tool for labelling the weekly
  unmatched log by language.
- **ZambiaSocialBERT** (`kelvinmbewe/ZambiaSocialBERT`, Apache-2.0, mBERT):
  English / Bemba / Nyanja / Lusaka slang / noisy classes, but trained on
  synthetic text and about 700 MB. Worth one comparison run on real
  transcripts, not adoption.
