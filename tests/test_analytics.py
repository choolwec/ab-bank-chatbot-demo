"""/admin/analytics: the dashboard's numbers match the weekly report's, the
filters scope everything, and nothing personal ever reaches the page or CSV.

The seed is test_report's (every number there is worked out by hand), so
"agrees with the report" is checked against the same rows.
"""

import csv
import datetime as dt
import io
import json
import sqlite3

import pytest

from admin import analytics, report
from app import audit, hours
from test_report import EXPECTED, PERSONAL, SESSIONS, _seed, _ticket

CREDS = ("cc-lead", "correct horse")
TODAY = dt.date(2026, 9, 24)


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", CREDS[0])
    monkeypatch.setenv("ADMIN_PASSWORD", CREDS[1])


@pytest.fixture
def seeded(isolated_data):
    _seed()


def last_week(channel=None):
    today = analytics.lusaka_today()
    return analytics.Window(today - dt.timedelta(days=6), today, channel)


# --- The date range ----------------------------------------------------------------------


def test_default_window_is_the_last_seven_days_including_today():
    w = analytics.parse_window(today=TODAY)
    assert (w.start, w.end, w.channel, w.days) == (dt.date(2026, 9, 18), TODAY, None, 7)


def test_window_bounds_are_lusaka_midnight_in_utc():
    w = analytics.Window(dt.date(2026, 9, 1), dt.date(2026, 9, 1), None)
    assert w.since == "2026-08-31T22:00:00+00:00"
    assert w.until == "2026-09-01T22:00:00+00:00"


@pytest.mark.parametrize("start, end, expected", [
    ("2026-09-20", "2026-09-10", (dt.date(2026, 9, 10), dt.date(2026, 9, 20))),  # swapped
    ("2026-09-01", "2027-01-01", (dt.date(2026, 9, 1), TODAY)),                 # never past today
    ("2020-01-01", "2026-09-24", (TODAY - dt.timedelta(days=365), TODAY)),      # capped at a year
    ("not-a-date", "2026-09-24'--", (dt.date(2026, 9, 18), TODAY)),            # junk -> default
])
def test_window_from_untrusted_values(start, end, expected):
    w = analytics.parse_window(start, end, today=TODAY)
    assert (w.start, w.end) == expected
    assert w.days <= analytics.MAX_DAYS


def test_unknown_channel_means_all_channels():
    assert analytics.parse_window(channel="<script>", today=TODAY).channel is None
    assert analytics.parse_window(channel="whatsapp", today=TODAY).channel == "whatsapp"


# --- Same numbers as the weekly report ------------------------------------------------------


REPORT_LINES = {
    "Conversations": "conversations",
    "Customer messages": "customer_messages",
    "Bot messages (not counting the welcome)": "bot_messages",
}


def test_traffic_matches_the_weekly_report_per_channel(seeded):
    data = analytics.build(last_week())
    tr = data["traffic"]
    for label, key in REPORT_LINES.items():
        total, web, whatsapp, messenger = (int(v.replace(",", "")) for v in EXPECTED[label])
        assert tr["totals"][key] == total, label
        assert [tr["by_channel"][c][key] for c in ("web", "whatsapp", "messenger")] == [web, whatsapp, messenger]


def test_every_shared_line_agrees_with_report_collect(seeded):
    """Not just the seeded values: the dashboard reads the report's own
    Traffic object, so every overlapping line is the same function."""
    w = last_week()
    con = sqlite3.connect(audit.DB_FILE)
    t = report.collect(con, w.since, w.until)
    con.close()
    data = analytics.build(w)
    assert data["understanding"]["typed_outcomes"]["not_understood"] == t.strikes(None) == 2
    assert data["understanding"]["fallback_rate"] == report._ratio(t.strikes(None), t.n(None, "user"))
    assert data["people"]["csat"] == {
        "asked": 3, "up": 2, "down": 1, "response_rate": 1.0, "score": t.csat_score(None),
    }
    assert data["health"]["delivery_failures"] == t.failures(None) == 3
    assert data["health"]["delivery_failure_rate"] == t.failure_rate(None)
    assert data["health"]["rate_limited"] == 1
    assert data["safety"]["urgent_confirmations_declined"] == 1


def test_tickets_and_leads_match_the_report(seeded):
    data = analytics.build(last_week())
    assert data["safety"]["tickets_by_type"] == {"callback": 4, "complaint": 1, "fraud": 2, "handoff": 1}
    m = data["marketing"]
    assert m["callbacks"] == 4
    assert m["callbacks_by_channel"] == {"web": 2, "whatsapp": 2}
    assert m["consent"] == {"yes": 1, "no": 1, "not asked": 1, "unknown": 1}
    assert m["consent_rate"] == 0.25
    sources = {c["source"]: c for c in m["campaigns"]}
    assert sources["qr_branch_cairo"]["callbacks"] == 2
    assert sources["facebook_ad"]["consenting_callbacks"] == 1


def test_consent_reads_any_yes_as_the_report_does(isolated_data):
    """D16: a stored "sure" is consent in the dashboard, the lead table and
    the campaign table alike."""
    audit.init_db()
    _ticket("callback", "web", {"topic": "a loan", "source": "radio", "marketing_consent": "sure"})
    data = analytics.build(last_week())
    assert data["marketing"]["consent"]["yes"] == 1
    assert data["marketing"]["campaigns"][0]["consenting_callbacks"] == 1
    assert "| radio | 0 | 1 | 1 |" in report.build_report(7, offline={}, run_offline=False)


# --- Filters --------------------------------------------------------------------------------


def test_channel_filter_scopes_every_section(seeded):
    data = analytics.build(last_week("whatsapp"))
    assert data["channels"] == ["whatsapp"]
    assert data["traffic"]["totals"]["conversations"] == 2
    assert data["safety"]["tickets_by_type"] == {"callback": 2, "complaint": 0, "fraud": 1, "handoff": 0}
    assert data["marketing"]["callbacks"] == 2
    assert data["people"]["csat"]["down"] == 1
    assert data["understanding"]["unmatched"] == []  # unmatched rows are all on the web


def test_date_range_excludes_older_and_later_rows(seeded):
    today = analytics.lusaka_today()
    old = analytics.build(analytics.Window(today - dt.timedelta(days=40), today - dt.timedelta(days=20), None))
    assert old["traffic"]["totals"]["conversations"] == 1  # the 30-day-old session
    assert old["traffic"]["totals"]["customer_messages"] == 1
    assert old["marketing"]["callbacks"] == 1
    yesterday = analytics.build(analytics.Window(today - dt.timedelta(days=7), today - dt.timedelta(days=1), None))
    assert yesterday["traffic"]["totals"]["customer_messages"] == 0
    assert yesterday["marketing"]["callbacks"] == 0


def test_daily_series_covers_every_day_and_adds_up(seeded):
    data = analytics.build(last_week())
    daily = data["traffic"]["daily"]
    assert [d["date"] for d in daily] == [d.isoformat() for d in last_week().dates()]
    assert sum(sum(d["user"].values()) for d in daily) == data["traffic"]["totals"]["customer_messages"]
    assert sum(sum(d["conv"].values()) for d in daily) == data["traffic"]["totals"]["conversations"]


# --- Lines only the dashboard has -----------------------------------------------------------


def _event(sid, role, text, action=None, intent=None, channel="web"):
    audit.log_event(sid, role, text, intent=intent, action=action, channel=channel)


def test_answers_are_split_into_typed_and_tapped_and_counted_once_per_turn(isolated_data):
    audit.init_db()
    _event("s1", "user", "what is etumba")
    _event("s1", "bot", "a", "answer", "etumba_what_is")
    _event("s1", "bot", "b", "answer", "etumba_what_is")  # second bubble, same turn
    _event("s1", "user", "[button] etumba_what_is")
    _event("s1", "bot", "a", "answer", "etumba_what_is")
    _event("s2", "user", "[button] human_handoff")
    _event("s2", "bot", "who", "flow_start", "human_handoff")
    _event("s3", "user", "talk to a person", channel="messenger")
    _event("s3", "bot", "ok", "handoff_inbox", "human_handoff", channel="messenger")
    data = analytics.build(last_week())
    assert data["understanding"]["top_intents"] == [
        {"intent": "etumba_what_is", "total": 2, "typed": 1, "tapped": 1}
    ]
    assert data["understanding"]["typed_outcomes"]["answered"] == 1
    assert data["people"]["talk_to_a_person"] == 2


def _raw_ticket(kind, created, transcript, fields=None, channel="web"):
    con = sqlite3.connect(audit.DB_FILE)
    con.execute(
        "INSERT INTO tickets (ref, type, created, status, fields, transcript, channel)"
        " VALUES (?, ?, ?, 'open', ?, ?, ?)",
        (f"T-{con.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]}", kind, created, json.dumps(fields or {}), json.dumps(transcript), channel),
    )
    con.commit()
    con.close()


def test_time_to_raise_counts_from_the_start_of_the_visit(isolated_data):
    audit.init_db()
    made = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = made.timestamp() - 300
    transcript = [
        {"role": "user", "text": "earlier visit", "ts": start - 3 * 3600},  # a different visit
        {"role": "user", "text": "hi", "ts": start},
        {"role": "user", "text": "my card was stolen", "ts": start + 60},
        {"role": "user", "text": "yesterday", "ts": start + 240},
    ]
    _raw_ticket("fraud", made.isoformat(), transcript, {"kind": "lost_card"})
    _raw_ticket("fraud", made.isoformat(), transcript[1:2])
    _raw_ticket("complaint", made.isoformat(), "not json")
    data = analytics.build(last_week())
    assert data["safety"]["reports"] == {"fraud": 1, "lost_card": 1, "complaint": 1}
    raised = data["safety"]["time_to_raise"]
    assert raised["fraud"] == {"n": 2, "median_minutes": 5.0, "p90_minutes": 5.0}
    assert raised["complaint"] == {"n": 0, "median_minutes": None, "p90_minutes": None}


def test_out_of_hours_uses_contact_centre_hours(isolated_data, monkeypatch):
    monkeypatch.setattr(analytics.hours, "is_open", lambda at: at.astimezone(hours.LUSAKA).hour == 10)
    audit.init_db()
    today = analytics.lusaka_today()
    at = lambda h: dt.datetime.combine(today, dt.time(h), hours.LUSAKA).astimezone(dt.timezone.utc)  # noqa: E731
    _raw_ticket("callback", at(10).isoformat(), [])
    _raw_ticket("callback", at(1).isoformat(), [], channel="whatsapp")
    data = analytics.build(analytics.Window(today, today, None))
    assert data["people"]["out_of_hours"]["callback"] == {"total": 2, "out_of_hours": 1, "share": 0.5}


# --- Privacy --------------------------------------------------------------------------------


def _identifiers():
    return PERSONAL + [s for sid, _, uh in SESSIONS.values() for s in (sid, uh)] + ["uhdeliveryhash01"]


def test_page_and_csv_carry_nothing_personal(client, seeded, admin_env):
    page = client.get("/admin/analytics", auth=CREDS)
    csv_text = client.get("/admin/analytics.csv", auth=CREDS).text
    assert page.status_code == 200
    for needle in _identifiers():
        assert needle not in page.text, needle
        assert needle not in csv_text, needle
    assert "call me on" not in page.text  # the unmatched message that still looked personal
    assert "withheld because they looked personal" in page.text


def test_page_is_self_contained_and_locked_down(client, seeded, admin_env):
    r = client.get("/admin/analytics?channel=web", auth=CREDS)
    assert "<script" not in r.text.lower()
    assert "http://" not in r.text and "https://" not in r.text  # no outside asset or tracker
    assert r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "set-cookie" not in r.headers
    assert "<option value='web' selected>" in r.text


def test_customer_text_is_escaped(client, isolated_data, admin_env):
    audit.init_db()
    _event("s9", "system", "<img src=x onerror=alert(1)>", "unmatched")
    r = client.get("/admin/analytics", auth=CREDS)
    assert "<img src=x" not in r.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in r.text


def test_csv_is_aggregates_with_formulas_neutralised(client, isolated_data, admin_env):
    audit.init_db()
    _ticket("callback", "web", {"topic": "a loan", "source": "=HYPERLINK(\"x\")"})
    _event("s9", "system", "some unmatched words", "unmatched")
    r = client.get("/admin/analytics.csv?channel=web", auth=CREDS)
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["section", "metric", "key", "channel", "value"]
    assert ["marketing", "campaign_callbacks", "'=HYPERLINK(\"x\")", "web", "1"] in rows
    assert not any(cell[:1] in "=+@" for row in rows for cell in row if cell)
    assert "some unmatched words" not in r.text  # free text stays off the CSV
    assert ["traffic", "conversations", "", "web", "0"] in rows


def test_cli_prints_json(isolated_data, capsys):
    audit.init_db()
    analytics.main(["--channel", "web"])
    assert json.loads(capsys.readouterr().out)["window"]["channel"] == "web"
