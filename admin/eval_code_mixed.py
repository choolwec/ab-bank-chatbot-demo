"""Code-mixed evaluation and model comparison (ticket N8).

Usage:
    python -m admin.eval_code_mixed                          # current matchers
    python -m admin.eval_code_mixed --model-dir <dir>        # + a candidate model

Reports, on tests/eval/code_mixed.yaml, how often each matcher gets the
right intent directly, and within one tap, for the character matcher, the
hybrid matcher with today's model, and optionally a candidate multilingual
model in ONNX form (same layout as models/all-MiniLM-L6-v2: tokenizer.json +
onnx/model.onnx).

Candidates named in the plan, both with licences that allow this use
([VERIFY] on the model card when downloading):
  - sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (Apache-2.0)
  - intfloat/multilingual-e5-small (MIT); prefix queries with "query: "
Neither lists Bemba or Nyanja among its training languages, so measure
before assuming a gain. Switch only if code-mixed accuracy improves AND the
E3 gates (both files) still pass.
"""

import argparse
from pathlib import Path

import yaml

from app import config

CODE_MIXED = config.BASE_DIR / "tests" / "eval" / "code_mixed.yaml"


def load():
    return yaml.safe_load(CODE_MIXED.read_text(encoding="utf-8"))


def score(matcher, items):
    direct = one_tap = 0
    for case in items:
        ranked = matcher.match(case["text"])
        if not ranked:
            continue
        top, s = ranked[0]
        if top == case["intent"] and s >= config.HIGH_CONFIDENCE:
            direct += 1
        if any(n == case["intent"] and sc >= config.MEDIUM_CONFIDENCE for n, sc in ranked[:3]):
            one_tap += 1
    n = max(1, len(items))
    return direct / n, one_tap / n


def main() -> None:
    parser = argparse.ArgumentParser(description="Code-mixed evaluation (N8)")
    parser.add_argument("--model-dir", type=Path, default=None, help="a candidate ONNX sentence model")
    args = parser.parse_args()
    from app import embedder
    from app.matcher import Matcher

    data = load()
    items = data["in_scope"]
    if data.get("seed_unverified"):
        print("WARNING: code_mixed.yaml is still the UNVERIFIED seed -- numbers are indicative only.\n")
    rows = [("character", Matcher(use_embeddings=False))]
    hybrid = Matcher(use_embeddings=True)
    if hybrid.mode == "hybrid":
        rows.append(("hybrid (all-MiniLM-L6-v2)", hybrid))
    if args.model_dir:
        candidate = embedder.Embedder(args.model_dir)  # candidates aren't hash-pinned: evaluation only
        rows.append((f"hybrid ({args.model_dir.name})", Matcher(use_embeddings=True, embedder=candidate)))
    print(f"{len(items)} code-mixed phrasings")
    for name, m in rows:
        d, t = score(m, items)
        print(f"  {name:32s} direct right {d:.1%}   within one tap {t:.1%}")


if __name__ == "__main__":
    main()
