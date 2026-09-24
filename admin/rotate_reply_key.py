"""Re-seal every stored reply address with the primary REPLY_KEY (ticket P7).

Usage:  python -m admin.rotate_reply_key [--check] [--dry-run] [--generate]

On the VM, run it through deploy/admin.sh so it sees the service's env file.
Rotating the key (docs/runbook-production.md, "Rotate REPLY_KEY"):

  1. --generate                 prints a new key
  2. REPLY_KEY=<new>,<old>      in the env file, then restart: new values are
                                sealed with the new key, old ones still open
  3. (no flags)                 re-seals every stored value with the new key
  4. --check                    must report 0 values on an old key
  5. REPLY_KEY=<new>            then restart; the old key is retired

Sealed values live in three places: inbox.db (`inbound.user_ref` and the
message's `phone_hint`), sessions.db (`slots.reply_ref` and
`slots.phone_hint_ref` in each session's state) and audit.db
(`tickets.reply_to.sealed`). Safe to run while the service is up: each row is
written only if it hasn't changed since it was read, so a customer's session
is never overwritten; a row that changed is counted and picked up by a second
run. Only counts are printed, never a value. A value no configured key opens
is left alone and reported: it was sealed with a key that is gone.
"""

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from app import audit, config, identity

SESSION_SLOTS = ("reply_ref", "phone_hint_ref")
BATCH = 500


@dataclass
class Tally:
    current: int = 0     # values already sealed with the primary key
    resealed: int = 0    # values re-sealed now (or that would be, with --dry-run)
    old: int = 0         # --check: values still on an old key
    unreadable: int = 0  # values no configured key opens
    changed: int = 0     # rows that moved while we worked; run again

    def line(self, name: str, check: bool) -> str:
        if check:
            return (f"{name}: {self.current} on the primary key, {self.old} on an old key,"
                    f" {self.unreadable} unreadable")
        return (f"{name}: {self.resealed} re-sealed, {self.current} already current,"
                f" {self.unreadable} unreadable, {self.changed} row(s) changed while running")


def _fresh(token, tally: Tally, check: bool) -> str | None:
    """The token re-sealed with the primary key, or None to leave it."""
    if not isinstance(token, str) or not token:
        return None
    if identity.sealed_with_primary(token):
        tally.current += 1
        return None
    try:
        new = identity.reseal(token)
    except (InvalidToken, ValueError, TypeError):
        tally.unreadable += 1
        return None
    if check:
        tally.old += 1
        return None
    return new


def _connect(path):
    return sqlite3.connect(path, timeout=10)


def _apply(con, updates, tally: Tally, dry_run: bool) -> None:
    """Compare-and-swap writes: each (sql, params, values) only lands if the
    row is exactly as read, so a concurrent change by the app always wins."""
    for i in range(0, len(updates), BATCH):
        with con:
            for sql, params, values in updates[i:i + BATCH]:
                if dry_run:
                    tally.resealed += values
                elif con.execute(sql, params).rowcount == 1:
                    tally.resealed += values
                else:
                    tally.changed += 1


def rotate_inbox(path, check=False, dry_run=False) -> Tally:
    tally = Tally()
    con = _connect(path)
    updates = []
    for row_id, user_ref, message in con.execute("SELECT id, user_ref, message FROM inbound").fetchall():
        new_ref = _fresh(user_ref, tally, check)
        record = json.loads(message)
        new_hint = _fresh(record.get("phone_hint"), tally, check)
        if new_ref is None and new_hint is None:
            continue
        new_message = message
        if new_hint is not None:
            record["phone_hint"] = new_hint
            new_message = json.dumps(record, ensure_ascii=False)
        updates.append((
            "UPDATE inbound SET user_ref = ?, message = ? WHERE id = ? AND user_ref IS ? AND message = ?",
            (new_ref or user_ref, new_message, row_id, user_ref, message),
            (new_ref is not None) + (new_hint is not None),
        ))
    _apply(con, updates, tally, dry_run)
    con.close()
    return tally


def rotate_sessions(path, check=False, dry_run=False) -> Tally:
    tally = Tally()
    con = _connect(path)
    updates = []
    for key, state in con.execute("SELECT key, state FROM sessions").fetchall():
        data = json.loads(state)
        slots = data.get("slots") or {}
        values = 0
        for slot in SESSION_SLOTS:
            new = _fresh(slots.get(slot), tally, check)
            if new is not None:
                slots[slot] = new
                values += 1
        if values:
            updates.append(("UPDATE sessions SET state = ? WHERE key = ? AND state = ?",
                            (json.dumps(data, ensure_ascii=False), key, state), values))
    _apply(con, updates, tally, dry_run)
    con.close()
    return tally


def rotate_tickets(path, check=False, dry_run=False) -> Tally:
    tally = Tally()
    con = _connect(path)
    updates = []
    rows = con.execute("SELECT ref, reply_to FROM tickets WHERE reply_to IS NOT NULL").fetchall()
    for ref, reply_to in rows:
        info = json.loads(reply_to)
        new = _fresh(info.get("sealed"), tally, check)
        if new is not None:
            info["sealed"] = new
            updates.append(("UPDATE tickets SET reply_to = ? WHERE ref = ? AND reply_to = ?",
                            (json.dumps(info, ensure_ascii=False), ref, reply_to), 1))
    _apply(con, updates, tally, dry_run)
    con.close()
    return tally


def targets() -> list[tuple[str, object, object]]:
    return [
        ("inbox.db", config.DATA_DIR / "inbox.db", rotate_inbox),
        ("sessions.db", config.DATA_DIR / "sessions.db", rotate_sessions),
        ("audit.db", audit.DB_FILE, rotate_tickets),
    ]


def rotate(check: bool = False, dry_run: bool = False) -> dict[str, Tally]:
    results = {}
    for name, path, fn in targets():
        if path.exists():
            results[name] = fn(path, check=check, dry_run=dry_run)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-seal stored reply addresses with the primary REPLY_KEY")
    parser.add_argument("--check", action="store_true", help="count values still on an old key; change nothing")
    parser.add_argument("--dry-run", action="store_true", help="count what would be re-sealed; change nothing")
    parser.add_argument("--generate", action="store_true", help="print a new Fernet key and exit")
    args = parser.parse_args()
    if args.generate:
        print(Fernet.generate_key().decode())
        return
    if not os.environ.get("REPLY_KEY") and not (config.DATA_DIR / identity._REPLY_KEY_FILE).exists():
        # Never generate a key here: that would mean the wrong environment.
        print(f"No REPLY_KEY set and no key file in {config.DATA_DIR}: is the service's env loaded?",
              file=sys.stderr)
        sys.exit(2)
    print(f"{len(identity.reply_keys())} key(s) configured; the first is primary.")
    results = rotate(check=args.check, dry_run=args.dry_run)
    if not results:
        print(f"No databases found in {config.DATA_DIR}.")
    for name, tally in results.items():
        print(tally.line(name, args.check))
    bad = sum(t.unreadable + t.changed + (t.old if args.check else 0) for t in results.values())
    if args.dry_run:
        print("Dry run: nothing written.")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
