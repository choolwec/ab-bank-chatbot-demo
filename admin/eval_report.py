"""Held-out evaluation at the production thresholds (ticket E3).

Usage:  python -m admin.eval_report [--all]

Prints the same numbers the CI gates check (tests/test_eval_gates.py
against tests/eval/gates.yaml), with the failing items listed:

  right_direct   in-scope questions answered directly with the right intent
  wrong_direct   in-scope questions answered directly with the WRONG intent
  oos_direct     out-of-scope questions answered directly (the dangerous one)
  one_tap        in-scope questions answered right, or offered in "did you
                 mean...?" -- i.e. reachable in at most one tap
  oos_suggested  out-of-scope questions that at least get a suggestion list

Measures the matcher alone (no urgent scan, no flows), so a routing change
elsewhere can't hide a matcher regression or vice versa.
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app import config

HELDOUT_FILE = config.BASE_DIR / "tests" / "eval" / "heldout.yaml"
GATES_FILE = config.BASE_DIR / "tests" / "eval" / "gates.yaml"


@dataclass
class EvalResult:
    metrics: dict
    wrong_direct: list = field(default_factory=list)   # (text, expected, got, score)
    oos_direct: list = field(default_factory=list)     # (text, got, score)
    missed: list = field(default_factory=list)         # (text, expected, top3)


def load_heldout(path: Path = HELDOUT_FILE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_gates(path: Path = GATES_FILE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["gates"]


def evaluate(matcher, heldout: dict | None = None) -> EvalResult:
    heldout = heldout or load_heldout()
    high, medium, n_suggest = (
        config.HIGH_CONFIDENCE, config.MEDIUM_CONFIDENCE, config.SUGGESTION_COUNT,
    )
    ins, oos = heldout["in_scope"], heldout["out_of_scope"]
    result = EvalResult(metrics={})
    right = wrong = one_tap = 0
    for case in ins:
        ranked = matcher.match(case["text"])
        top, score = ranked[0] if ranked else (None, 0.0)
        suggested = [n for n, s in ranked[:n_suggest] if s >= medium]
        if score >= high:
            if top == case["intent"]:
                right += 1
                one_tap += 1
            else:
                wrong += 1
                result.wrong_direct.append((case["text"], case["intent"], top, round(score, 3)))
        elif case["intent"] in suggested:
            one_tap += 1
        else:
            result.missed.append((case["text"], case["intent"], [(n, round(s, 2)) for n, s in ranked[:3]]))
    oos_direct = oos_suggested = 0
    for case in oos:
        ranked = matcher.match(case["text"])
        top, score = ranked[0] if ranked else (None, 0.0)
        if score >= high:
            oos_direct += 1
            result.oos_direct.append((case["text"], top, round(score, 3)))
        if score >= medium:
            oos_suggested += 1
    result.metrics = {
        "right_direct": round(right / len(ins), 3),
        "wrong_direct": round(wrong / len(ins), 3),
        "oos_direct": round(oos_direct / len(oos), 3),
        "one_tap": round(one_tap / len(ins), 3),
        "oos_suggested": round(oos_suggested / len(oos), 3),
        "n_in_scope": len(ins),
        "n_out_of_scope": len(oos),
    }
    return result


def check_gates(metrics: dict, gates: dict) -> list[str]:
    """Human-readable gate failures; empty means every gate passes."""
    failures = []
    for name, limit in gates.items():
        metric, kind = name.rsplit("_", 1)
        value = metrics[metric]
        if kind == "min" and value < limit:
            failures.append(f"{metric} = {value:.3f} is below the gate {limit:.3f}")
        if kind == "max" and value > limit:
            failures.append(f"{metric} = {value:.3f} is above the gate {limit:.3f}")
    return failures


def format_report(result: EvalResult, gates: dict, show_all: bool = False) -> str:
    m = result.metrics
    lines = [
        f"Held-out: {m['n_in_scope']} in-scope, {m['n_out_of_scope']} out-of-scope "
        f"(HIGH {config.HIGH_CONFIDENCE}, MEDIUM {config.MEDIUM_CONFIDENCE})",
        "",
    ]
    for name, limit in gates.items():
        metric, kind = name.rsplit("_", 1)
        op = ">=" if kind == "min" else "<="
        ok = not check_gates({metric: m[metric]}, {name: limit})
        lines.append(f"  {'PASS' if ok else 'FAIL'}  {metric:<14} {m[metric]:.3f}   gate {op} {limit:.3f}")
    lines.append(f"        oos_suggested  {m['oos_suggested']:.3f}   (informational)")
    lines += ["", "Out-of-scope questions answered DIRECTLY:"]
    lines += [f"  {s:.2f}  {t!r} -> {g}" for t, g, s in result.oos_direct] or ["  (none)"]
    lines += ["", "In-scope questions answered with the WRONG intent:"]
    lines += [f"  {s:.2f}  {t!r} -> {g} (expected {e})" for t, e, g, s in result.wrong_direct] or ["  (none)"]
    if show_all:
        lines += ["", "In-scope questions neither answered nor suggested:"]
        lines += [f"  {t!r} (expected {e}) top3={top}" for t, e, top in result.missed] or ["  (none)"]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Held-out evaluation vs the E3 gates")
    parser.add_argument("--all", action="store_true", help="also list items not reachable in one tap")
    args = parser.parse_args()
    from app.matcher import Matcher

    result = evaluate(Matcher())
    print(format_report(result, load_gates(), show_all=args.all))


if __name__ == "__main__":
    main()
