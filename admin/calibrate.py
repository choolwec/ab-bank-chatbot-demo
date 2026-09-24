"""Threshold calibration for the embedding decision (ticket N5).

Usage:  python -m admin.calibrate [--oos-target 0.03] [--seed 7]

1. Pools every labelled set -- tests/eval/heldout.yaml, banking77.yaml and
   golden.yaml (in-scope) plus heldout's, oos.yaml's and banking77's
   out-of-scope items -- and splits EACH source 50/50 into calibration and
   test halves with a fixed seed.
2. On the CALIBRATION half only, picks EMB_HIGH: the lowest threshold that
   keeps out-of-scope direct answers at or below --oos-target (3%, the §1
   target), and EMB_MEDIUM: the lowest threshold that keeps out-of-scope
   "did you mean" offers at or below --oos-suggest-target (45%: stricter than
   the character matcher, and low enough that gibberish falls back).
3. Reports the TEST half at those thresholds against the §1 targets
   (right >= 85%, wrong <= 2%, out-of-scope <= 3%).

It never tunes on the test half. The output is the config patch to apply
(and to justify in the commit), not an automatic change.
"""

import argparse
import random

from app import config
from admin.eval_report import ABSTAIN_INTENTS, load_banking77, load_heldout, load_oos


def _golden():
    path = config.BASE_DIR / "tests" / "eval" / "golden.yaml"
    if not path.exists():
        return {"in_scope": [], "out_of_scope": []}
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"in_scope": [], "out_of_scope": []}


def pooled_sets(seed: int):
    """(cal_in, cal_oos, test_in, test_oos), each split per source."""
    heldout, b77, golden = load_heldout(), load_banking77(), _golden()
    ins_sources = {"heldout": heldout["in_scope"], "banking77": b77["in_scope"], "golden": golden["in_scope"]}
    oos_sources = {
        "heldout": heldout["out_of_scope"], "oos": load_oos(),
        "banking77": b77["out_of_scope"], "golden": golden["out_of_scope"],
    }
    rng = random.Random(seed)
    cal_in, test_in, cal_oos, test_oos = [], [], [], []
    for items in ins_sources.values():
        items = list(items)
        rng.shuffle(items)
        half = len(items) // 2
        cal_in += items[:half]
        test_in += items[half:]
    for items in oos_sources.values():
        items = list(items)
        rng.shuffle(items)
        half = len(items) // 2
        cal_oos += items[:half]
        test_oos += items[half:]
    return cal_in, cal_oos, test_in, test_oos


def score_items(matcher, items, with_label=True):
    """(top intent, raw embedding similarity of the top intent, gold intent)."""
    out = []
    for case in items:
        d = matcher.detail(case["text"])
        ranked = matcher.match(case["text"], top_n=1)
        top = ranked[0][0] if ranked else None
        emb = d["emb"].get(top, 0.0) if top else 0.0
        if ranked and ranked[0][1] >= 1.0:
            emb = 1.0  # an exact phrase match is certain
        out.append((top, emb, case.get("intent") if with_label else None))
    return out


def rates(ins, oos, high, medium=None):
    n_in, n_oos = max(1, len(ins)), max(1, len(oos))
    right = sum(1 for top, e, gold in ins if top not in ABSTAIN_INTENTS and e >= high and top == gold) / n_in
    wrong = sum(1 for top, e, gold in ins if top not in ABSTAIN_INTENTS and e >= high and top != gold) / n_in
    oos_direct = sum(1 for top, e, _ in oos if top not in ABSTAIN_INTENTS and e >= high) / n_oos
    out = {"right": right, "wrong": wrong, "oos_direct": oos_direct}
    if medium is not None:
        out["oos_suggested"] = sum(1 for top, e, _ in oos if top not in ABSTAIN_INTENTS and e >= medium) / n_oos
    return out


def choose(values, ok):
    """The lowest candidate threshold for which ok(threshold) holds."""
    for thr in sorted(set(values)):
        if ok(thr):
            return thr
    return 1.0


def calibrate(matcher, seed=7, oos_target=0.03, oos_suggest_target=0.45):
    cal_in, cal_oos, test_in, test_oos = pooled_sets(seed)
    ci, co = score_items(matcher, cal_in), score_items(matcher, cal_oos, with_label=False)
    ti, to = score_items(matcher, test_in), score_items(matcher, test_oos, with_label=False)
    candidates = [round(x / 200, 3) for x in range(40, 200)]  # 0.200 .. 0.995
    high = choose(candidates, lambda t: rates(ci, co, t)["oos_direct"] <= oos_target)
    medium = choose(
        [c for c in candidates if c < high],
        lambda t: rates(ci, co, high, t)["oos_suggested"] <= oos_suggest_target,
    )
    medium = min(medium, round(high - 0.05, 3))
    return {
        "EMB_HIGH": high, "EMB_MEDIUM": medium,
        "calibration": dict(rates(ci, co, high, medium), n_in=len(ci), n_oos=len(co)),
        "test": dict(rates(ti, to, high, medium), n_in=len(ti), n_oos=len(to)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate EMB_HIGH / EMB_MEDIUM (never on the test split)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--oos-target", type=float, default=0.03)
    parser.add_argument("--oos-suggest-target", type=float, default=0.45)
    args = parser.parse_args()
    from app.matcher import Matcher

    matcher = Matcher(use_embeddings=True)
    if matcher.mode != "hybrid":
        raise SystemExit("embedding model unavailable: run `python -m admin.fetch_model` first")
    r = calibrate(matcher, args.seed, args.oos_target, args.oos_suggest_target)
    c, t = r["calibration"], r["test"]
    print(f"EMB_HIGH = {r['EMB_HIGH']:.3f}   EMB_MEDIUM = {r['EMB_MEDIUM']:.3f}   (seed {args.seed})")
    print(f"calibration ({c['n_in']} in / {c['n_oos']} oos): right {c['right']:.1%}  wrong {c['wrong']:.1%}  "
          f"oos direct {c['oos_direct']:.1%}  oos suggested {c['oos_suggested']:.1%}")
    print(f"TEST        ({t['n_in']} in / {t['n_oos']} oos): right {t['right']:.1%}  wrong {t['wrong']:.1%}  "
          f"oos direct {t['oos_direct']:.1%}  oos suggested {t['oos_suggested']:.1%}")
    print("§1 targets: right >= 85%, wrong <= 2%, out-of-scope direct <= 3%")
    print(f"\npatch app/config.py:\n  EMB_HIGH = {r['EMB_HIGH']:.3f}\n  EMB_MEDIUM = {r['EMB_MEDIUM']:.3f}")


if __name__ == "__main__":
    main()
