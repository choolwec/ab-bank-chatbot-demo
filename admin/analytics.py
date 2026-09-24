"""The numbers behind /admin/analytics (and its CSV export).

    python -m admin.analytics --from 2026-09-01 --to 2026-09-24 [--channel whatsapp] [--csv]

One date range (Lusaka days, both ends included) and an optional channel
scope everything. The calculations are admin.report's own (collect,
load_tickets, top_unmatched, campaign_counts, _consent, topic_group), so the
dashboard and the weekly report never disagree: a line both show is the
same function over the same rows.

Counts only. No name, phone number, session id, user hash or transcript is
ever returned. The only free text is the masked unmatched messages and the
campaign codes, filtered by the same looks_personal() check as the report;
the CSV carries no free text except campaign codes, and neutralises any
cell a spreadsheet would run as a formula.
"""

import argparse
import collections
import csv
import datetime as dt
import io
import json
import sqlite3
import statistics
import sys
from dataclasses import dataclass

from admin import report
from app import audit, config, hours

MAX_DAYS = 366
DEFAULT_DAYS = 7
PRESETS = (7, 30, 90)
TOP_INTENTS = 15
UNMATCHED = 15
URGENT_TYPES = ("fraud", "complaint")
# Tickets that promise a person will pick them up: the out-of-hours question.
PICKUP_TYPES = ("callback", "complaint", "handoff", "fraud")
# Bot turns that answer the customer with an intent (typed or tapped).
INTENT_ACTIONS = ("answer", "out_of_scope", "flow_start", "handoff_inbox")


@dataclass(frozen=True)
class Window:
    start: dt.date  # Lusaka dates, both included
    end: dt.date
    channel: str | None  # None = every channel

    @property
    def since(self) -> str:
        return _utc(self.start)

    @property
    def until(self) -> str:
        return _utc(self.end + dt.timedelta(days=1))

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def dates(self) -> list[dt.date]:
        return [self.start + dt.timedelta(days=i) for i in range(self.days)]


def _utc(day: dt.date) -> str:
    """Midnight in Lusaka on `day`, as the UTC ISO string the audit log uses."""
    moment = dt.datetime.combine(day, dt.time(0), hours.LUSAKA).astimezone(dt.timezone.utc)
    return moment.isoformat(timespec="seconds")


def lusaka_today() -> dt.date:
    """Today in Lusaka, from the real clock (hours.now() is pinned in tests
    to an in-hours moment; the audit log's timestamps are not)."""
    return dt.datetime.now(hours.LUSAKA).date()


def parse_window(start=None, end=None, channel=None, today: dt.date | None = None) -> Window:
    """A Window from untrusted query values. Anything unreadable falls back
    to the default (the last 7 days, today included); a range is capped at
    MAX_DAYS and never runs past today."""
    today = today or lusaka_today()

    def day(value):
        try:
            return dt.date.fromisoformat(str(value)) if value else None
        except ValueError:
            return None

    end_day = min(day(end) or today, today)
    start_day = day(start) or end_day - dt.timedelta(days=DEFAULT_DAYS - 1)
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    if (end_day - start_day).days >= MAX_DAYS:
        start_day = end_day - dt.timedelta(days=MAX_DAYS - 1)
    return Window(start_day, end_day, channel if channel in report.CHANNELS else None)


def preset(days: int, today: dt.date | None = None) -> Window:
    today = today or lusaka_today()
    return Window(today - dt.timedelta(days=days - 1), today, None)


# --- Reads not in the weekly report ----------------------------------------------------


def _channel_sql(window: Window, where: str, params: tuple) -> tuple[str, tuple]:
    if window.channel is None:
        return where, params
    return where + " AND channel = ?", params + (window.channel,)


def daily_traffic(con, window: Window) -> list[dict]:
    """Per Lusaka day and channel: conversations (distinct sessions with a
    customer message), customer messages and bot messages (not the welcome),
    the same definitions as report.collect."""
    where, params = _channel_sql(window, *report._window("ts", window.since, window.until))
    rows = con.execute(
        "SELECT date(ts, '+2 hours') AS day, channel, "
        "COUNT(DISTINCT CASE WHEN role = 'user' THEN session_id END), "
        "SUM(role = 'user'), SUM(role = 'bot' AND COALESCE(action, '') != 'welcome') "
        f"FROM events WHERE {where} GROUP BY day, channel",
        params,
    ).fetchall()
    by_day = {d.isoformat(): {"date": d.isoformat(), "conv": {}, "user": {}, "bot": {}} for d in window.dates()}
    for day, channel, conv, user, bot in rows:
        entry = by_day.get(day)
        if entry is None:
            continue
        ch = channel or "web"
        entry["conv"][ch] = conv
        entry["user"][ch] = user or 0
        entry["bot"][ch] = bot or 0
    return list(by_day.values())


def intent_turns(con, window: Window) -> tuple[collections.Counter, collections.Counter]:
    """(typed, tapped): bot turns per (action, intent), split by whether the
    customer typed the message or tapped a button. One turn counts once,
    however many bubbles it had (as report.collect counts turns)."""
    where, params = _channel_sql(window, *report._window("ts", window.since, window.until))
    typed, tapped = collections.Counter(), collections.Counter()
    last_user, prev = {}, None
    for session_id, role, text, action, intent in con.execute(
        "SELECT session_id, role, text, action, intent FROM events "
        f"WHERE role IN ('user', 'bot') AND {where} ORDER BY session_id, id",
        params,
    ):
        if role == "user":
            last_user[session_id] = text or ""
        elif action in INTENT_ACTIONS and intent and prev != (session_id, "bot", action):
            tap = last_user.get(session_id, "").startswith("[button] ")
            (tapped if tap else typed)[action, intent] += 1
        prev = (session_id, role, action)
    return typed, tapped


def _minutes_to_raise(created: str, transcript_raw: str) -> float | None:
    """Minutes from the start of the visit to the ticket: the ticket's
    transcript walked back from its end until a gap longer than
    IDLE_REGREET_MINUTES (the widget would have greeted again there)."""
    try:
        turns = json.loads(transcript_raw or "[]")
        stamps = [float(t["ts"]) for t in turns if isinstance(t, dict) and t.get("ts") is not None]
        made = dt.datetime.fromisoformat(created).timestamp()
    except (ValueError, TypeError, KeyError):
        return None
    if not stamps:
        return None
    gap = config.IDLE_REGREET_MINUTES * 60
    start = stamps[-1]
    for earlier in reversed(stamps[:-1]):
        if start - earlier > gap:
            break
        start = earlier
    return max(0.0, (made - start) / 60)


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, -(-len(ordered) * p // 100) - 1)
    return ordered[int(index)]


def ticket_details(con, window: Window) -> list[dict]:
    where, params = _channel_sql(window, *report._window("created", window.since, window.until))
    out = []
    for kind, channel, created, raw, transcript in con.execute(
        "SELECT type, channel, created, fields, CASE WHEN type IN ('fraud', 'complaint') "
        f"THEN transcript END FROM tickets WHERE {where}", params
    ):
        try:
            fields = json.loads(raw or "{}")
        except ValueError:
            fields = {}
        out.append({
            "type": kind,
            "channel": channel or "web",
            "created": created,
            "fields": fields if isinstance(fields, dict) else {},
            "minutes": _minutes_to_raise(created, transcript) if kind in URGENT_TYPES else None,
        })
    return out


def _out_of_hours(created: str) -> bool:
    try:
        return not hours.is_open(dt.datetime.fromisoformat(created))
    except ValueError:
        return False


# --- The dashboard's numbers ---------------------------------------------------------------


def build(window: Window) -> dict:
    audit.init_db()
    con = sqlite3.connect(audit.DB_FILE)
    try:
        t = report.collect(con, window.since, window.until)
        daily = daily_traffic(con, window)
        typed, tapped = intent_turns(con, window)
        tickets = ticket_details(con, window)
        unmatched, withheld = report.top_unmatched(con, window.since, window.until, window.channel, UNMATCHED)
        campaigns = report.campaign_counts(con, window.since, window.until, window.channel)
        where, params = _channel_sql(window, *report._window("ts", window.since, window.until))
        abandoned = con.execute(
            f"SELECT COUNT(*) FROM events WHERE action = 'jira_push_abandoned' AND {where}", params
        ).fetchone()[0]
    finally:
        con.close()
    ch = window.channel
    channels = [ch] if ch else t.ordered_channels()

    return {
        "window": {"from": window.start.isoformat(), "to": window.end.isoformat(),
                   "days": window.days, "channel": ch or "all"},
        "channels": channels,
        "traffic": _traffic(t, ch, channels, daily),
        "understanding": _understanding(t, ch, typed, tapped, unmatched, withheld),
        "safety": _safety(t, ch, tickets),
        "people": _people(t, ch, typed, tapped, tickets),
        "marketing": _marketing(tickets, campaigns),
        "health": _health(t, ch, abandoned),
    }


def _traffic(t, ch, channels, daily) -> dict:
    n = t.n

    def line(c):
        return {"conversations": n(c, "conv"), "customer_messages": n(c, "user"),
                "bot_messages": n(c, "bot"), "bot_per_conversation": t.per_conversation(c, n(c, "bot"))}

    return {"totals": line(ch), "by_channel": {c: line(c) for c in channels}, "daily": daily}


def _understanding(t, ch, typed, tapped, unmatched, withheld) -> dict:
    n = t.n
    answered = sum(v for (action, _), v in typed.items() if action == "answer")
    outcomes = {
        "answered": answered,
        "suggested": n(ch, "turn:did_you_mean"),
        "not_understood": t.strikes(ch),
        "out_of_scope": n(ch, "turn:out_of_scope"),
    }
    by_intent = collections.Counter()
    for (action, intent), v in list(typed.items()) + list(tapped.items()):
        if action == "answer":
            by_intent[intent] += v
    top = [
        {"intent": intent, "total": total, "typed": typed["answer", intent], "tapped": tapped["answer", intent]}
        for intent, total in sorted(by_intent.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_INTENTS]
    ]
    return {
        "typed_outcomes": outcomes,
        "typed_total": sum(outcomes.values()),
        "fallback_rate": report._ratio(t.strikes(ch), n(ch, "user")),
        "top_intents": top,
        "repairs": {
            "two_strike_offers": n(ch, "turn:two_strike"),
            "repeat": n(ch, "turn:repeat"),
            "clarify": n(ch, "turn:clarify"),
            "frustration": n(ch, "turn:frustration"),
            "context_boosts": n(ch, "sys:context_boost"),
            "two_questions_answered": n(ch, "sys:multi_answer"),
        },
        "unmatched": [{"text": text, "count": count} for text, count in unmatched],
        "unmatched_withheld": withheld,
    }


def _summary(values: list[float]) -> dict:
    return {
        "n": len(values),
        "median_minutes": round(statistics.median(values), 1) if values else None,
        "p90_minutes": round(_percentile(values, 90), 1) if values else None,
    }


def _safety(t, ch, tickets) -> dict:
    n = t.n
    by_type = collections.Counter(tk["type"] for tk in tickets)
    fraud_kinds = collections.Counter(
        "lost_card" if tk["fields"].get("kind") == "lost_card" else "fraud"
        for tk in tickets if tk["type"] == "fraud"
    )
    raise_time = {
        kind: _summary([tk["minutes"] for tk in tickets if tk["type"] == kind and tk["minutes"] is not None])
        for kind in URGENT_TYPES
    }
    return {
        "reports": {"fraud": fraud_kinds["fraud"], "lost_card": fraud_kinds["lost_card"],
                    "complaint": by_type["complaint"]},
        "urgent_flows_started": n(ch, "turn:urgent:*"),
        "urgent_confirmations_asked": n(ch, "turn:urgent_confirm:*"),
        "urgent_confirmations_declined": n(ch, "turn:urgent_declined"),
        "time_to_raise": raise_time,
        "tickets_by_type": {k: by_type[k] for k in sorted({"fraud", "complaint", "callback", "handoff"} | set(by_type))},
    }


def _people(t, ch, typed, tapped, tickets) -> dict:
    n = t.n
    handoff_asks = sum(
        v for counter in (typed, tapped) for (_, intent), v in counter.items() if intent == "human_handoff"
    )
    out_of_hours = {}
    for kind in PICKUP_TYPES:
        made = [tk["created"] for tk in tickets if tk["type"] == kind]
        out = sum(1 for c in made if _out_of_hours(c))
        out_of_hours[kind] = {"total": len(made), "out_of_hours": out, "share": report._ratio(out, len(made))}
    return {
        "talk_to_a_person": handoff_asks,
        "two_strike_offers": n(ch, "turn:two_strike"),
        "handoff_tickets": sum(1 for tk in tickets if tk["type"] == "handoff"),
        "callbacks": sum(1 for tk in tickets if tk["type"] == "callback"),
        "paused_messages": n(ch, "sys:paused"),
        "out_of_hours": out_of_hours,
        "csat": {
            "asked": n(ch, "sys:csat_asked"),
            "up": n(ch, "turn:csat:up"),
            "down": n(ch, "turn:csat:down"),
            "response_rate": report._ratio(t.csat_answers(ch), n(ch, "sys:csat_asked")),
            "score": t.csat_score(ch),
        },
    }


def _marketing(tickets, campaigns) -> dict:
    callbacks = [tk for tk in tickets if tk["type"] == "callback"]
    consent = collections.Counter(report._consent(tk["fields"]) for tk in callbacks)
    by_channel = collections.Counter(tk["channel"] for tk in callbacks)
    topics = collections.Counter(report.topic_group(tk["fields"].get("topic", "")) for tk in callbacks)
    sources = []
    for source, sessions, cbs, consenting in campaigns["rows"]:
        clean = report._clean_value(source)
        sources.append({"source": "(withheld)" if clean is None else (clean or "unknown"),
                        "sessions": sessions, "callbacks": cbs, "consenting_callbacks": consenting})
    return {
        "callbacks": len(callbacks),
        "callbacks_by_channel": dict(by_channel),
        "consent": {k: consent[k] for k in (*report.CONSENT_ROWS, "unknown")},
        "consent_rate": report._ratio(consent["yes"], len(callbacks)),
        "topics": [{"topic": k, "callbacks": v} for k, v in topics.most_common()],
        "campaigns": sources,
        "opt_outs": campaigns["opt_outs"],
    }


def _health(t, ch, abandoned) -> dict:
    n = t.n
    return {
        "delivery_failures": t.failures(ch),
        "delivery_failure_rate": t.failure_rate(ch),
        "rate_limited": n(ch, "sys:rate_limited"),
        "desk_failed": n(ch, "sys:desk_failed"),
        "jira_push_abandoned": abandoned,
    }


# --- CSV ---------------------------------------------------------------------------------


def _safe(value) -> str:
    """A cell a spreadsheet will not run as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def csv_rows(data: dict) -> list[list]:
    """Long format: section, metric, key, channel, value. Aggregates only; no
    customer free text (the unmatched messages are left out)."""
    w = data["window"]
    scope = w["channel"]
    rows = [["section", "metric", "key", "channel", "value"],
            ["window", "from", "", scope, w["from"]], ["window", "to", "", scope, w["to"]]]

    def add(section, metric, value, key="", channel=scope):
        rows.append([section, metric, key, channel, "" if value is None else value])

    tr = data["traffic"]
    for metric, value in tr["totals"].items():
        add("traffic", metric, value)
    for channel, line in tr["by_channel"].items():
        for metric, value in line.items():
            add("traffic", metric, value, channel=channel)
    for day in tr["daily"]:
        for metric in ("conv", "user", "bot"):
            for channel, value in sorted(day[metric].items()):
                add("traffic_daily", {"conv": "conversations", "user": "customer_messages",
                                      "bot": "bot_messages"}[metric], value, key=day["date"], channel=channel)

    u = data["understanding"]
    for metric, value in u["typed_outcomes"].items():
        add("understanding", "typed_" + metric, value)
    add("understanding", "fallback_rate", u["fallback_rate"])
    for metric, value in u["repairs"].items():
        add("understanding", metric, value)
    for item in u["top_intents"]:
        add("understanding", "answers_by_intent", item["total"], key=item["intent"])
    add("understanding", "unmatched_withheld", u["unmatched_withheld"])

    s = data["safety"]
    for metric, value in s["reports"].items():
        add("safety", "reports", value, key=metric)
    for metric in ("urgent_flows_started", "urgent_confirmations_asked", "urgent_confirmations_declined"):
        add("safety", metric, s[metric])
    for kind, summary in s["time_to_raise"].items():
        for metric, value in summary.items():
            add("safety", "time_to_raise_" + metric, value, key=kind)
    for kind, value in s["tickets_by_type"].items():
        add("safety", "tickets", value, key=kind)

    p = data["people"]
    for metric in ("talk_to_a_person", "two_strike_offers", "handoff_tickets", "callbacks", "paused_messages"):
        add("people", metric, p[metric])
    for kind, line in p["out_of_hours"].items():
        add("people", "tickets", line["total"], key=kind)
        add("people", "tickets_out_of_hours", line["out_of_hours"], key=kind)
    for metric, value in p["csat"].items():
        add("people", "csat_" + metric, value)

    m = data["marketing"]
    add("marketing", "callbacks", m["callbacks"])
    for channel, value in m["callbacks_by_channel"].items():
        add("marketing", "callbacks", value, channel=channel)
    for key, value in m["consent"].items():
        add("marketing", "consent", value, key=key)
    add("marketing", "consent_rate", m["consent_rate"])
    add("marketing", "opt_outs", m["opt_outs"])
    for item in m["topics"]:
        add("marketing", "callbacks_by_topic", item["callbacks"], key=item["topic"])
    for item in m["campaigns"]:
        for metric in ("sessions", "callbacks", "consenting_callbacks"):
            add("marketing", "campaign_" + metric, item[metric], key=item["source"])

    for metric, value in data["health"].items():
        add("health", metric, value)
    return [[_safe(cell) for cell in row] for row in rows]


def to_csv(data: dict) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerows(csv_rows(data))
    return buffer.getvalue()


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Dashboard numbers (the /admin/analytics data)")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    parser.add_argument("--channel", choices=report.CHANNELS)
    parser.add_argument("--csv", action="store_true", help="CSV instead of JSON")
    args = parser.parse_args(argv)
    data = build(parse_window(args.start, args.end, args.channel))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(to_csv(data) if args.csv else json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
