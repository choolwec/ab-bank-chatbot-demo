# Evaluation data (tickets E3, N1, N2)

| File | What | Source | Gate |
|---|---|---|---|
| `heldout.yaml` | 91 in-scope + 30 out-of-scope phrasings, written from each intent's label/topic | Our own (E3) | `right_direct`, `wrong_direct`, `oos_direct`, `one_tap` |
| `oos.yaml` | 304 out-of-scope questions, many hard lookalikes | Our own (N2) | `oos_large_direct` |
| `banking77.yaml` | 360 in-scope (mapped) + 360 out-of-scope | BANKING77, CC BY 4.0 (below) | `b77_*` |
| `golden.yaml` | Real customer phrasings, two agreeing reviewers | Staff trial / production (N1) | added once it holds >= 30 per intent |
| `gates.yaml` | The thresholds CI enforces, with their history | | |

Run `python -m admin.eval_report --all` for the numbers and the failing items.
**Never copy an evaluation phrasing into an intent's `phrases:`**
(`tests/test_eval_gates.py` enforces it). A test phrase that becomes a training
phrase stops measuring anything.

## Growing the golden set (N1)

1. `python -m admin.export_utterances --days 30`: masked customer messages
   to `data/utterances.csv`, with the current prediction and what the bot did.
   Anything that still looks personal is dropped.
2. Two reviewers fill `label_a` and `label_b` independently, with an intent
   name or `oos`.
3. `python -m admin.import_labels data/utterances.csv`: agreed rows are
   merged into `golden.yaml`, and disagreements are printed for the PO.
4. The staff workshop (W04) adds phrasings per intent the same way. The
   target is at least 30 per intent.

## BANKING77 attribution

`banking77.yaml` is adapted from **BANKING77** by Iñigo Casanueva, Tadas
Temčinas, Daniela Gerz, Matthew Henderson and Ivan Vulić (PolyAI), from
"Efficient Intent Detection with Dual Sentence Encoders" (2020),
https://github.com/PolyAI-LDN/task-specific-datasets, licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Changes: only the
test split, only the labels mapped in `admin/import_banking77.py` (9 onto
our intents, 9 neobank features treated as out of scope), whitespace
normalised, duplicates removed. Regenerate with
`python -m admin.import_banking77`. The mapping is one reviewer's judgement
and needs a second reviewer before it informs a launch decision.
