"""Calibrate EMB_URGENT for the model-based urgent check (ticket N7).

Usage:  python -m admin.calibrate_urgent [--max-false 0.02]

Tunes ONLY on the BANKING77 train split (fetched on the fly, not stored)
plus our own negative sets, and reports the BANKING77 test split
(tests/eval/banking77.yaml) as the untouched check:

  recall gain   of the urgent reports the rules MISS, the share the model catches
  false rate    non-urgent messages the rules leave alone but the model
                flags (each costs the customer one "report it as fraud?" question)

EMB_URGENT is the lowest threshold keeping the false rate at or below
--max-false (2%, the N7 acceptance) on the tuning data.
"""

import argparse
import csv
import io

import httpx

from app import guards

TRAIN_URL = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv"


def _rules_miss(text):
    s = guards.urgent_scan(text)
    return not (s and s.kind == "fraud") and not guards.urgent_negated(text)


def tuning_sets():
    from admin.eval_report import load_heldout, load_oos
    from admin.import_banking77 import IN_SCOPE
    from pathlib import Path

    urgent_labels = {k for k, v in IN_SCOPE.items() if v in ("fraud_scam", "lost_stolen_card")}
    rows = list(csv.DictReader(io.StringIO(httpx.get(TRAIN_URL, timeout=60, follow_redirects=True).text)))
    pos = [r["text"] for r in rows if r["category"] in urgent_labels]
    neg = [r["text"] for r in rows if r["category"] not in urgent_labels and r["category"] != "lost_or_stolen_phone"]
    ours = [l.strip() for l in (Path("tests/data/urgent_negative.txt")).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    ours += [c["text"] for c in load_heldout()["in_scope"] if c["intent"] not in ("fraud_scam", "lost_stolen_card", "complaint")]
    ours += [c["text"] for c in load_oos()]
    return pos, neg + ours


def test_sets():
    from admin.eval_report import load_banking77

    b77 = load_banking77()
    pos = [c["text"] for c in b77["in_scope"] if c["intent"] in ("fraud_scam", "lost_stolen_card")]
    neg = [c["text"] for c in b77["in_scope"] if c["intent"] not in ("fraud_scam", "lost_stolen_card")]
    neg += [c["text"] for c in b77["out_of_scope"]]
    return pos, neg


def measure(sim, pos, neg, thr):
    missed = [t for t in pos if _rules_miss(t)]
    quiet = [t for t in neg if _rules_miss(t)]
    gain = sum(sim[t] >= thr for t in missed) / max(1, len(missed))
    false = sum(sim[t] >= thr for t in quiet) / max(1, len(quiet))
    total = (len(pos) - len(missed) + sum(sim[t] >= thr for t in missed)) / max(1, len(pos))
    return {"gain": gain, "false": false, "recall": total, "missed": len(missed), "quiet": len(quiet)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate EMB_URGENT")
    parser.add_argument("--max-false", type=float, default=0.02)
    args = parser.parse_args()
    from app import urgent_model

    tpos, tneg = tuning_sets()
    xpos, xneg = test_sets()
    texts = set(tpos) | set(tneg) | set(xpos) | set(xneg)
    sim = {t: urgent_model.similarity(t) for t in texts}
    if any(v is None for v in sim.values()):
        raise SystemExit("embedding model unavailable: run `python -m admin.fetch_model` first")
    thr = next((round(x / 200, 3) for x in range(100, 200)
                if measure(sim, tpos, tneg, round(x / 200, 3))["false"] <= args.max_false), 1.0)
    tune, test = measure(sim, tpos, tneg, thr), measure(sim, xpos, xneg, thr)
    print(f"EMB_URGENT = {thr:.3f}")
    print(f"tuning (BANKING77 train + ours): recall {tune['recall']:.1%}; of {tune['missed']} rule misses the model "
          f"catches {tune['gain']:.1%}; false {tune['false']:.2%} of {tune['quiet']}")
    print(f"TEST   (BANKING77 test):          recall {test['recall']:.1%}; of {test['missed']} rule misses the model "
          f"catches {test['gain']:.1%}; false {test['false']:.2%} of {test['quiet']}")


if __name__ == "__main__":
    main()
