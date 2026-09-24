"""Export customer messages for labelling (ticket N1).

Usage:  python -m admin.export_utterances --days 30 [--out data/utterances.csv]

Writes one row per distinct customer message from the audit log, with what
the CURRENT matcher predicts and what the bot did at the time:

    text, predicted_intent, score, action, label_a, label_b, source

`label_a` / `label_b` are left empty for two reviewers to fill in (an intent
name, or "oos" for out of scope). `source` is "audit" here; H4's
admin/export_bot_wrong.py appends the messages agents tagged, as
"bot-wrong". `python -m admin.import_labels` turns the reviewed file into
tests/eval/golden.yaml.

The audit log is already masked (guards run before storage). As a SECOND
check this drops anything that still looks personal: phone numbers, email
addresses, long digit runs, masked placeholders, and button taps.
"""

import argparse
import csv
import datetime as dt
import re
import sqlite3
from pathlib import Path

from app import audit, config, guards

PERSONAL_RE = re.compile(
    r"\d{6,}|\+?\d[\d \-]{8,}\d|[^@\s]+@[^@\s]+\.[a-z]{2,}|\[(?:CARD|NRC|ACCOUNT|PHONE)? ?REDACTED\]",
    re.IGNORECASE,
)
FIELDS = ["text", "predicted_intent", "score", "action", "label_a", "label_b", "source"]


def looks_personal(text: str) -> bool:
    _, findings = guards.mask(text)
    return bool(findings) or bool(PERSONAL_RE.search(text))


def export(days: int) -> list[dict]:
    from app.matcher import Matcher

    matcher = Matcher()
    audit.init_db()
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds")
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute(
        "SELECT id, session_id, text FROM events WHERE role = 'user' AND ts >= ? ORDER BY id", (since,)
    ).fetchall()
    out, seen = [], set()
    for event_id, session_id, text in rows:
        text = " ".join((text or "").split())
        if not text or text.startswith("[") or looks_personal(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        nxt = con.execute(
            "SELECT action FROM events WHERE session_id = ? AND id > ? AND role = 'bot' ORDER BY id LIMIT 1",
            (session_id, event_id),
        ).fetchone()
        ranked = matcher.match(text)
        top, score = ranked[0] if ranked else ("", 0.0)
        out.append({"text": text, "predicted_intent": top, "score": f"{score:.3f}",
                    "action": (nxt[0] if nxt else "") or "", "label_a": "", "label_b": "", "source": "audit"})
    con.close()
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Export masked customer messages for labelling")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--out", type=Path, default=config.DATA_DIR / "utterances.csv")
    args = parser.parse_args()
    rows = export(args.days)
    with args.out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"written: {args.out} ({len(rows)} messages)")


if __name__ == "__main__":
    main()
