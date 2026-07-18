"""Weekly metrics report (build plan §6).

Usage:  python -m admin.report --days 7 [--out data/report.md]

Headline metrics plus the single biggest quality lever at this scale: the
top unmatched utterances, which become new intent phrasings each week.
"""

import argparse
import datetime as dt
import sqlite3
from pathlib import Path

from app import audit


def _since(days: int) -> str:
    return (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    ).isoformat(timespec="seconds")


def build_report(days: int) -> str:
    audit.init_db()
    con = sqlite3.connect(audit.DB_FILE)
    since = _since(days)

    def one(sql, *params):
        return con.execute(sql, params).fetchone()[0]

    sessions = one(
        "SELECT COUNT(DISTINCT session_id) FROM events WHERE role='user' AND ts >= ?",
        since,
    )
    user_msgs = one(
        "SELECT COUNT(*) FROM events WHERE role='user' AND ts >= ?", since
    )
    actions = dict(
        con.execute(
            "SELECT action, COUNT(*) FROM events WHERE role='bot' AND ts >= ? "
            "AND action IS NOT NULL GROUP BY action",
            (since,),
        ).fetchall()
    )
    tickets = dict(
        con.execute(
            "SELECT type, COUNT(*) FROM tickets WHERE created >= ? GROUP BY type",
            (since,),
        ).fetchall()
    )
    unmatched = con.execute(
        "SELECT lower(text), COUNT(*) AS n FROM events WHERE action='unmatched' "
        "AND ts >= ? GROUP BY lower(text) ORDER BY n DESC LIMIT 20",
        (since,),
    ).fetchall()
    con.close()

    fallbacks = actions.get("fallback", 0) + actions.get("two_strike", 0)
    fallback_rate = (fallbacks / user_msgs * 100) if user_msgs else 0.0
    escalations = tickets.get("callback", 0)
    escalation_rate = (escalations / sessions * 100) if sessions else 0.0

    lines = [
        f"# Chatbot weekly report — last {days} days",
        f"Generated {dt.date.today().isoformat()}",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Sessions | {sessions} |",
        f"| User messages | {user_msgs} |",
        f"| Fallback rate (fallback + two-strike / user msgs) | {fallback_rate:.1f}% |",
        f"| Escalation rate (callbacks / sessions) | {escalation_rate:.1f}% |",
        f"| Tickets: fraud | {tickets.get('fraud', 0)} |",
        f"| Tickets: complaint | {tickets.get('complaint', 0)} |",
        f"| Tickets: callback | {escalations} |",
        "",
        "## Bot actions",
        "",
        "| Action | Count |",
        "|---|---|",
    ]
    for action, count in sorted(actions.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {action} | {count} |")
    lines += [
        "",
        "## Top unmatched utterances (feed these back into intents/*.yaml)",
        "",
    ]
    if unmatched:
        lines += ["| Utterance (masked) | Count |", "|---|---|"]
        lines += [f"| {text} | {n} |" for text, n in unmatched]
    else:
        lines.append("None in this window.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly chatbot metrics report")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=Path, default=None, help="write markdown here")
    args = parser.parse_args()
    report = build_report(args.days)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
