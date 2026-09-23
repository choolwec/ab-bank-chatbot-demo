# Matcher benchmark: current matcher vs small local models

This is research code, not part of the app or its test suite. It measures how
well the free-text matcher handles **phrasings nobody on the team wrote**, and
how well it **declines questions the bot doesn't cover**. For a bank, the second
of those matters more.

- `tests/eval/heldout.yaml` holds the test set (moved from `heldout_v0.py`
  by ticket E3; the CI evaluation gates read the same file).
  - 91 in-scope customer phrasings, written from each intent's *label and topic*
    rather than copied from the YAML `phrases:`. They include misspellings and
    Zambian English.
  - 30 out-of-scope questions. Most are deliberate "hard" lookalikes, such as
    "how do I open a facebook account" or "what time does shoprite close".
- `bench_matcher.py` holds the benchmark. It always evaluates the current
  matcher. Set `MINILM_DIR` to add the small-model variants (see the script
  docstring).

## Results (2026-09-23, CPU, one process)

| System | Top-1 accuracy | ms/query | At ≤10% of out-of-scope answered: right | wrong |
|---|---|---|---|---|
| Current matcher (TF-IDF char n-grams + fuzzy) | 89.0% | ~2 | 37.4% | 2.2% |
| all-MiniLM-L6-v2 embeddings (22M params, ONNX) | 89.0% | ~2.5 | 74.7% | 4.4% |
| Hybrid 50/50 | 94.5% | ~5 | 61.5% | 3.3% |
| **Hybrid rank + embedding gate** | **94.5%** | ~5 | **74.7%** | **3.3%** |
| Supervised head (logistic regression on embeddings) | 92.3% | ~2.5 | 51.6% | 0.0% |

The **current matcher at its production thresholds** gives these results:

- At `HIGH_CONFIDENCE` 0.70 (direct answer), it answers 53.8% of in-scope
  questions correctly and 4.4% wrongly. It **directly answers 26.7% of the
  out-of-scope questions** (8 of 30), for example:
  - "i need a lawyer" → how to apply for a loan
  - "how do i open a facebook account" → account opening
  - "what time does shoprite close" → our opening hours
- At `MEDIUM_CONFIDENCE` 0.45 ("did you mean…?"), it offers a suggestion on 73.3%
  of out-of-scope questions.

**What this shows:**

- **The two scorers fail on different things.** Character n-grams handle
  misspellings ("hw do i opn an acount"). Embeddings handle meaning ("internet
  banking is down" means a technical issue, not a forgotten password). Ranking
  with both lifts top-1 accuracy from 89% to 94.5%.
- **Embeddings separate "ours" from "not ours" much better.** Using the embedding
  score to decide *whether* to answer doubles the share of questions that get a
  correct direct answer at the same out-of-scope exposure (37% → 75%).
- A plain supervised head is very precise but spreads its probability thinly
  over 50 intents. It would need an explicit out-of-scope class trained on
  negative examples, the approach used with the CLINC150 dataset.

## Caveats (read before quoting these numbers)

- **The set is small and self-written:** 121 items, written by the same person
  who ran the benchmark. It gives a direction, not a definitive figure. The real
  evaluation set should come from masked production transcripts, staff-written
  phrasings and BANKING77-mapped queries (see `docs/excellence-plan.md` §5).
- **Thresholds were picked on the test set** to compare systems at equal
  out-of-scope exposure. A production threshold must be fitted on a separate
  calibration set.
- **Where the model file came from.** Hugging Face was unreachable from the
  research environment. The ONNX model was taken from the npm package
  `@xcidos/genesis-memory-model@0.1.0-alpha.1` (Apache-2.0, no install scripts,
  `model.onnx` sha256 `6fd5d72f…6452`), a third-party repackaging of
  all-MiniLM-L6-v2. It behaves like a sentence encoder (paraphrase similarity
  0.72, unrelated 0.05). **For production, fetch the model from the official
  source and pin its hash.**
