"""Weekly shadow-mode review (ticket N4).

Usage:  python -m admin.shadow_report --days 7 [--out data/shadow.md]

Lists every message where the live (character) decision and the shadow
(hybrid) decision disagree, grouped by the intents involved, with the masked
customer text, so reviewers can mark which was right. Acceptance for
switching production over (N4): two consecutive weekly reviews where the
shadow decision is right on >= 80% of disagreements and never worse on
out-of-scope questions.
"""

import argparse
import collections
import datetime as dt
import json
import sqlite3
from pathlib import Path

from app import audit


def disagreements(days: int) -> tuple[list[dict], int]:
    audit.init_db()
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds")
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute(
        "SELECT id, session_id, text FROM events WHERE action = 'shadow' AND ts >= ? ORDER BY id", (since,)
    ).fetchall()
    out = []
    for event_id, session_id, raw in rows:
        record = json.loads(raw)
        if record.get("agree"):
            continue
        user = con.execute(
            "SELECT text FROM events WHERE session_id = ? AND role = 'user' AND id < ? ORDER BY id DESC LIMIT 1",
            (session_id, event_id),
        ).fetchone()
        out.append(dict(record, text=user[0] if user else ""))
    con.close()
    return out, len(rows)


def build(days: int) -> str:
    items, total = disagreements(days)
    lines = [
        f"# Shadow-mode review: last {days} days",
        "",
        f"{total} free-text messages scored by both matchers; **{len(items)} disagreements**"
        + (f" ({len(items) / total:.1%})." if total else "."),
        "",
        "For each, tick which decision was right. Switch production to the hybrid",
        "matcher only after two weekly reviews with the shadow right on >= 80% of",
        "disagreements and never worse on out-of-scope questions.",
    ]
    groups = collections.defaultdict(list)
    for d in items:
        groups[(d["live"]["intent"] or "-", d["shadow"]["intent"] or "-")].append(d)
    for (live, shadow), group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines += ["", f"## live `{live}` vs shadow `{shadow}` ({len(group)})", "",
                  "| Message | Live | Shadow | Right? |", "|---|---|---|---|"]
        for d in group:
            fmt = lambda x: f"{x['decision']} {x['score']:.2f}"
            text = d["text"].replace("|", "/")
            lines.append(f"| {text} | {fmt(d['live'])} | {fmt(d['shadow'])} | live / shadow / neither |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Shadow-mode disagreements for review")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build(args.days)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        import sys

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(report)


if __name__ == "__main__":
    main()
