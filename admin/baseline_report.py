"""Metrics snapshot: the "before" (E4) and every later "after" picture.

Usage:  python -m admin.baseline_report [--out docs/metrics-baseline.md]

Collects, in one place and at one commit:
  - E3 held-out metrics vs the gates
  - E2 conversation scripts: passed / expected failures
  - S1/S3 urgent and red-team suites: passed / failed
  - bot bubbles and customer turns per scripted path (fraud report,
    complaint, callback, branch lookup, FAQ answer)
Runs everything against a temporary data dir; never touches data/.
"""

import argparse
import datetime as dt
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from app import audit, config

ROOT = config.BASE_DIR

# Each path is the shortest happy path a customer can take today.
PATHS = {
    "Fraud report (free-text trigger)": [
        ("say", "someone stole money from my etumba"),
        ("say", "they took K500 after a call pretending to be the bank"),
        ("say", "yesterday"),
        ("say", "eTumba"),
        ("say", "0977123456"),
        ("tap", "confirm_yes"),
    ],
    "Lost card": [
        ("say", "i lost my card"),
        ("say", "lost it at the market"),
        ("say", "today"),
        ("say", "card"),
        ("say", "0977123456"),
        ("tap", "confirm_yes"),
    ],
    "Complaint": [
        ("say", "I want to complain"),
        ("say", "Service at a branch"),
        ("say", "I waited two hours and nobody helped me"),
        ("say", "skip"),
        ("tap", "confirm_yes"),
    ],
    "Callback request": [
        ("tap", "human_handoff"),
        ("say", "Mary Banda"),
        ("say", "0977123456"),
        ("say", "Opening a business account"),
        ("tap", "Morning"),
        ("tap", "confirm_yes"),
    ],
    "Branch lookup": [
        ("tap", "branch_locator"),
        ("tap", "loc_branch"),
        ("say", "Kitwe"),
    ],
    "FAQ answer": [
        ("say", "what is etumba"),
    ],
}


def _isolate():
    tmp = Path(tempfile.mkdtemp(prefix="abz-baseline-"))
    config.DATA_DIR = tmp
    audit.DB_FILE = tmp / "audit.db"
    audit.JSONL_FILE = tmp / "audit.jsonl"
    audit._init_done = False


def measure_paths() -> list[tuple[str, int, int, int]]:
    """(path, customer turns, bot bubbles excl. welcome, max bubbles in one turn)."""
    _isolate()
    from app import router
    from app.session import SessionStore

    rows = []
    for name, turns in PATHS.items():
        session, _ = SessionStore().get_or_create()
        router.welcome(session)
        bubbles = worst = 0
        for kind, value in turns:
            if kind == "say":
                replies, _ = router.handle(session, text=value)
            else:
                replies, _ = router.handle(session, payload=value)
            bubbles += len(replies)
            worst = max(worst, len(replies))
        rows.append((name, len(turns), bubbles, worst))
    return rows


def _pytest_summary(*targets: str) -> str:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    lines = [l for l in out.strip().splitlines() if l.strip()]
    last = lines[-1] if lines else "no output"
    return re.sub(r"=+", "", re.sub(r"\s+in [\d.]+s.*$", "", last)).strip()


def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
        ).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def build(title: str) -> str:
    from admin.eval_report import check_gates, evaluate, load_gates
    from app.matcher import Matcher

    result = evaluate(Matcher())
    gates = load_gates()
    m = result.metrics
    paths = measure_paths()

    out = [
        f"# {title}",
        "",
        f"Generated {dt.date.today():%Y-%m-%d} at commit `{_commit()}` by "
        "`python -m admin.baseline_report`. Every later claim of improvement is "
        "measured against a report like this one.",
        "",
        "## Understanding (E3 held-out set, production thresholds)",
        "",
        f"{m['n_in_scope']} in-scope and {m['n_out_of_scope']} out-of-scope questions; "
        f"direct answer at >= {config.HIGH_CONFIDENCE}, suggestions at >= {config.MEDIUM_CONFIDENCE}.",
        "",
        "| Metric | Value | Gate | Target (excellence plan §1) |",
        "|---|---|---|---|",
    ]
    targets = {
        "right_direct": ">= 0.85", "wrong_direct": "<= 0.02",
        "oos_direct": "<= 0.03", "one_tap": "—",
    }
    for name, limit in gates.items():
        metric, kind = name.rsplit("_", 1)
        op = ">=" if kind == "min" else "<="
        status = "" if not check_gates({metric: m[metric]}, {name: limit}) else " **FAIL**"
        out.append(f"| {metric} | {m[metric]:.3f}{status} | {op} {limit:.3f} | {targets.get(metric, '—')} |")
    out.append(f"| oos_suggested | {m['oos_suggested']:.3f} | — | — |")
    out += ["", "Out-of-scope questions answered directly:", ""]
    out += [f"- {s:.2f} “{t}” → `{g}`" for t, g, s in result.oos_direct] or ["- none"]
    out += ["", "In-scope questions answered with the wrong intent:", ""]
    out += [f"- {s:.2f} “{t}” → `{g}` (expected `{e}`)" for t, e, g, s in result.wrong_direct] or ["- none"]

    out += [
        "",
        "## Conversation and safety suites",
        "",
        "| Suite | Result |",
        "|---|---|",
        f"| E2 conversation scripts (`tests/test_conversations.py`) | {_pytest_summary('tests/test_conversations.py')} |",
        f"| S1 urgent detection (`tests/test_urgent.py`) | {_pytest_summary('tests/test_urgent.py')} |",
        f"| S3 red-team routing (`tests/test_redteam_routing.py`) | {_pytest_summary('tests/test_redteam_routing.py')} |",
        f"| Full suite | {_pytest_summary()} |",
        "",
        "## Message budget per path",
        "",
        "Bot bubbles the customer receives on the shortest happy path, not "
        "counting the welcome. Target: <= 4 bot messages per fraud report (M1).",
        "",
        "| Path | Customer turns | Bot bubbles | Most bubbles in one turn |",
        "|---|---|---|---|",
    ]
    out += [f"| {name} | {turns} | {bubbles} | {worst} |" for name, turns, bubbles, worst in paths]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Metrics snapshot")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--title", default="Metrics snapshot")
    args = parser.parse_args()
    report = build(args.title)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
