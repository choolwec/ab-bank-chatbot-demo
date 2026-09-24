"""Turn a reviewed labelling CSV into tests/eval/golden.yaml (ticket N1).

Usage:  python -m admin.import_labels data/utterances.csv [--out tests/eval/golden.yaml]

Each row needs two labels (label_a, label_b): an intent name, or "oos". A
row goes into the golden set only when BOTH reviewers agree; disagreements
are printed for the PO to decide. Unknown intent names are rejected. Rows
already in the golden set are kept; the file is merged, not overwritten.
"""

import argparse
import csv
from pathlib import Path

import yaml

from app import config

GOLDEN_FILE = config.BASE_DIR / "tests" / "eval" / "golden.yaml"
OOS_LABELS = {"oos", "out_of_scope"}


def import_rows(rows: list[dict], known_intents: set[str], golden: dict | None = None):
    golden = golden or {"in_scope": [], "out_of_scope": []}
    have = {c["text"].lower() for c in golden["in_scope"] + golden["out_of_scope"]}
    disagreements, unknown, added = [], [], 0
    for row in rows:
        text = " ".join((row.get("text") or "").split())
        a = (row.get("label_a") or "").strip().lower()
        b = (row.get("label_b") or "").strip().lower()
        if not text or not a or not b:
            continue
        if a != b:
            disagreements.append((text, a, b))
            continue
        if text.lower() in have:
            continue
        if a in OOS_LABELS:
            golden["out_of_scope"].append({"text": text, "source": "labelled"})
        elif a in known_intents:
            golden["in_scope"].append({"text": text, "intent": a, "source": "labelled"})
        else:
            unknown.append((text, a))
            continue
        have.add(text.lower())
        added += 1
    return golden, added, disagreements, unknown


HEADER = """# N1 golden evaluation set: real customer phrasings, each label agreed by
# TWO reviewers (admin/import_labels.py). Grows from the staff trial and
# production traffic via admin/export_utterances.py. Never copy these into
# intent phrases (a test enforces it).
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a reviewed labelling CSV")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--out", type=Path, default=GOLDEN_FILE)
    args = parser.parse_args()
    from app.matcher import Matcher

    known = set(Matcher().intents)
    golden = yaml.safe_load(args.out.read_text(encoding="utf-8")) if args.out.exists() else None
    with args.csv.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    golden, added, disagreements, unknown = import_rows(rows, known, golden)
    args.out.write_text(HEADER + "\n" + yaml.safe_dump(golden, sort_keys=False, allow_unicode=True, width=110),
                        encoding="utf-8")
    print(f"written: {args.out} (+{added})")
    for text, a, b in disagreements:
        print(f"  DISAGREE ({a} vs {b}): {text}")
    for text, label in unknown:
        print(f"  UNKNOWN INTENT {label!r}: {text}")


if __name__ == "__main__":
    main()
