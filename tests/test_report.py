"""H6: the weekly quality report, from a seeded temporary audit DB.

Every number asserted here is worked out by hand from the seed below.
"""

import datetime as dt
import json
import sqlite3

import pytest

from admin import report
from app import audit, config

SESSIONS = {
    "W1": ("sess-web-one-9f2c41", "web", "uh7f3a9c0d1e2b4455"),
    "W2": ("sess-web-two-81ad07", "web", "uhb1c2d3e4f5061728"),
    "A1": ("sess-wa-one-44be19", "whatsapp", "uh0a1b2c3d4e5f6071"),
    "A2": ("sess-wa-two-c0de55", "whatsapp", "uh99887766554433aa"),
    "M1": ("sess-ms-one-77aa20", "messenger", "uhfeedfacecafe0123"),
}
CALLBACKS = [
    ("web", {"name": "Mwila Tembo", "phone": "0977123456", "topic": "A loan", "time": "Morning",
             "source": "facebook_ad", "marketing_consent": "yes"}),
    ("web", {"name": "Chanda Phiri", "phone": "0966555444", "topic": "Opening a business account",
             "time": "Afternoon", "marketing_consent": "no"}),
    ("whatsapp", {"name": "Bupe Zulu", "phone": "0955111222", "topic": "a loan", "time": "Morning",
                  "source": "qr_branch_cairo"}),
    ("whatsapp", {"name": "Natasha Mumba", "phone": "0977000111", "topic": "call me on 0977 000 111",
                  "time": "Morning", "source": "qr_branch_cairo", "marketing_consent": "not_asked"}),
]
PERSONAL = ["0977123456", "0966555444", "0955111222", "0977000111", "0977 000 111",
            "Mwila", "Tembo", "Chanda", "Phiri", "Bupe", "Zulu", "Natasha", "Mumba"]
OFFLINE = {
    "right_direct": 0.90, "wrong_direct": 0.02, "oos_direct": 0.05, "one_tap": 0.95,
    "b77_urgent_recall": 0.75, "gates": {"b77_urgent_recall_min": 0.754},
    "redteam_recall": 1.0, "redteam_caught": 109, "redteam_n": 109,
    "redteam_hard_false": 0, "redteam_neg_n": 49, "mode": "char",
}


def _ago(days):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat(timespec="seconds")


class Seed:
    def __init__(self, key):
        self.sid, self.channel, self.uh = SESSIONS[key]

    def user(self, text):
        audit.log_event(self.sid, "user", text, channel=self.channel, user_hash=self.uh)
        return self

    def bot(self, action, bubbles=1):
        for _ in range(bubbles):
            audit.log_event(self.sid, "bot", "reply", action=action, channel=self.channel, user_hash=self.uh)
        return self

    def system(self, action, text="x"):
        audit.log_event(self.sid, "system", text, action=action, channel=self.channel, user_hash=self.uh)
        return self

    def turn(self, text, action, bubbles=1):
        return self.user(text).bot(action, bubbles)


def _ticket(kind, channel, fields, created=None):
    con = sqlite3.connect(audit.DB_FILE)
    con.execute(
        "INSERT INTO tickets (ref, type, created, status, fields, transcript, channel)"
        " VALUES (?, ?, ?, 'open', ?, '[]', ?)",
        (f"{kind[:3].upper()}-{con.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]}",
         kind, created or _ago(0), json.dumps(fields), channel),
    )
    con.commit()
    con.close()


def _seed():
    audit.init_db()
    w1 = Seed("W1")
    w1.bot("welcome")
    w1.turn("what is etumba", "answer")
    w1.user("flurb").system("unmatched", "flurb").bot("fallback")
    w1.user("zzz qqq").system("unmatched", "zzz qqq").bot("two_strike")
    w1.turn("repeat", "repeat")
    w1.turn("what do you mean", "clarify")
    w1.turn("my card number", "answer", bubbles=2)  # PII warning + answer: one turn
    w1.turn("what are your hours?", "digression:lead")
    w1.user("sorry my number is 0966123456").system("correction", "correction: lead.phone").bot("flow:lead")
    w1.turn("cancel", "cancel_confirm")
    w1.turn("yes", "cancel")
    w1.user("thanks").system("csat_asked").bot("answer")
    w1.turn("[button] csat:up", "csat:up")

    w2 = Seed("W2")
    w2.bot("welcome")
    w2.turn("you are useless", "frustration")
    w2.turn("rubbish", "abuse")
    w2.user("passport renewal").system("unmatched", "call me on 0977123456").bot("out_of_scope")
    w2.turn("my money is gone", "urgent_confirm:fraud")
    w2.turn("no", "urgent_declined")
    w2.user("tamanga fees").system("context_boost").bot("answer")
    w2.user("hours and kitwe").system("multi_answer").bot("answer")
    w2.user("loans").system("shadow", json.dumps({"agree": True})).bot("answer")
    w2.user("etumba").system("shadow", json.dumps({"agree": False})).bot("answer")

    a1 = Seed("A1")
    a1.turn("hi", "answer")
    a1.turn("someone stole my money", "urgent:fraud")
    a1.turn("yesterday", "flow:fraud")
    a1.turn("0977123456", "flow:fraud")
    a1.user("thanks").system("csat_asked").bot("answer")
    a1.turn("[button] csat:down", "csat:down")
    a1.system("rate_limited")
    a1.user("hello?").system("paused")

    a2 = Seed("A2")
    a2.turn("hi", "answer")
    a2.turn("cancel", "cancel_confirm")
    a2.turn("no", "cancel_declined")
    a2.user("thanks").system("csat_asked").bot("answer")
    a2.turn("[button] csat:up", "csat:up")

    m1 = Seed("M1")
    m1.turn("hi", "answer")
    m1.turn("where is kitwe", "flow_start")

    def delivery(action, channel, text="x"):
        audit.log_event("-", "system", text, action=action, channel=channel, user_hash="uhdeliveryhash01")

    delivery("wa_status:failed", "whatsapp")
    delivery("send_failed", "whatsapp")
    for _ in range(3):
        delivery("wa_status:delivered", "whatsapp")
    delivery("template:case_update", "whatsapp", "case_update template for CBK-1: sent")
    delivery("template:case_update", "whatsapp", "case_update template for CBK-2: sent")
    delivery("template:case_update", "whatsapp", "case_update template for CBK-3: failed")
    delivery("send_failed", "messenger")

    # Outside the 7-day window: must not count anywhere.
    con = sqlite3.connect(audit.DB_FILE)
    for role, action in (("user", None), ("bot", "fallback"), ("system", "csat_asked")):
        con.execute(
            "INSERT INTO events (ts, session_id, role, text, action, channel) VALUES (?, ?, ?, ?, ?, ?)",
            (_ago(30), "sess-old-000000", role, "old", action, "web"),
        )
    con.commit()
    con.close()
    _ticket("callback", "web", {"topic": "old loan"}, created=_ago(30))

    for channel, fields in CALLBACKS:
        _ticket("callback", channel, fields)
    _ticket("fraud", "web", {"what_happened": "x"})
    _ticket("fraud", "whatsapp", {"what_happened": "x"})
    _ticket("complaint", "web", {"topic": "x"})
    _ticket("handoff", "messenger", {"reason": "customer asked for a person"})


@pytest.fixture
def seeded(isolated_data):
    _seed()
    return report.build_report(7, offline=OFFLINE)


def cells(text, label):
    """The cells after the label in the first table row starting with it."""
    for line in text.splitlines():
        if line.startswith(f"| {label} |"):
            return [c.strip() for c in line.strip().strip("|").split("|")][1:]
    raise AssertionError(f"no row {label!r}")


def section(text, heading):
    start = text.index(heading)
    rest = text[start + len(heading):]
    ends = [i for i in (rest.find("\n## "), rest.find("\n### ")) if i >= 0]
    return rest[: min(ends)] if ends else rest


def channel_row(text, label):
    """[all, web, whatsapp, messenger] of a per-channel line (after Source)."""
    return cells(text, label)[1:]


# --- every H6 line, per channel ------------------------------------------------------

EXPECTED = {
    "Conversations": ["5", "2", "2", "1"],
    "Customer messages": ["35", "21", "12", "2"],
    "Bot messages (not counting the welcome)": ["35", "22", "11", "2"],
    "Bot messages per conversation": ["7.00", "11.00", "5.50", "2.00"],
    "Strikes": ["2", "2", "0", "0"],
    "Strikes per conversation": ["0.40", "1.00", "0.00", "0.00"],
    "Fallback rate": ["5.7%", "9.5%", "0.0%", "0.0%"],
    "Two-strike handoff offers": ["1", "1", "0", "0"],
    "Repairs: repeat": ["1", "1", "0", "0"],
    "Repairs: clarify": ["1", "1", "0", "0"],
    "Frustration": ["1", "1", "0", "0"],
    "Abuse": ["1", "1", "0", "0"],
    "Out of scope": ["1", "1", "0", "0"],
    "Context boosts": ["1", "1", "0", "0"],
    "Two questions answered in one reply": ["1", "1", "0", "0"],
    "Shadow matcher: messages scored": ["2", "2", "0", "0"],
    "Shadow matcher: agreement": ["50.0%", "50.0%", "—", "—"],
    "Digressions answered and resumed": ["1", "1", "0", "0"],
    "Corrections": ["1", "1", "0", "0"],
    "Cancel confirmations asked": ["2", "1", "1", "0"],
    "Flows cancelled": ["1", "1", "0", "0"],
    "Carried on after the cancel question": ["1", "0", "1", "0"],
    "Urgent confirmations asked": ["1", "1", "0", "0"],
    "Urgent flows started": ["1", "0", "1", "0"],
    "Urgent confirmations declined": ["1", "1", "0", "0"],
    "Delivery failures": ["3", "0", "2", "1"],
    "Delivery failure rate": ["23.1%", "—", "18.2%", "50.0%"],
    "Rate limited": ["1", "0", "1", "0"],
    "Paused (a person has the conversation)": ["1", "0", "1", "0"],
    "CSAT asked": ["3", "1", "2", "0"],
    "CSAT thumbs up": ["2", "1", "1", "0"],
    "CSAT thumbs down": ["1", "0", "1", "0"],
    "CSAT response rate": ["100.0%", "100.0%", "100.0%", "—"],
    "CSAT score (out of 5)": ["3.33", "5.00", "2.50", "—"],
}


@pytest.mark.parametrize("label", sorted(EXPECTED))
def test_every_line_per_channel(seeded, label):
    assert channel_row(seeded, label) == EXPECTED[label]


def test_channel_columns_and_sources(seeded):
    assert "| Line | Source | All | web | whatsapp | messenger |" in seeded
    assert cells(seeded, "Corrections")[0] == "`correction`"
    assert cells(seeded, "Two questions answered in one reply")[0] == "`multi_answer`"
    assert cells(seeded, "Digressions answered and resumed")[0] == "`digression:*`"


def test_tickets_by_type_and_channel(seeded):
    table = section(seeded, "## Tickets by type and channel")
    assert cells(table, "callback") == ["4", "2", "2", "0"]  # the 30-day-old one is out
    assert cells(table, "fraud") == ["2", "1", "1", "0"]
    assert cells(table, "complaint") == ["1", "1", "0", "0"]
    assert cells(table, "handoff") == ["1", "0", "0", "1"]
    assert cells(table, "**Total**") == ["8", "4", "3", "1"]


def test_whatsapp_cost_uses_the_free_tier_and_rate(seeded):
    table = section(seeded, "## Estimated WhatsApp cost")
    assert cells(table, "WhatsApp bot messages")[1] == "11"
    assert cells(table, "Free service messages for 7 days")[1] == "233"  # 1,000 x 7/30
    assert cells(table, "Billable service messages")[1] == "0"
    assert cells(table, "Utility templates sent (always billable)")[1] == "2"  # the failed one isn't
    assert cells(table, "**Estimated cost**")[1] == "US$ 0.01"  # 2 x 0.004
    assert cells(table, "Estimated cost per WhatsApp conversation")[1] == "US$ 0.0040"
    assert "[VERIFY]" in cells(table, "Rate per message")[0]


def test_whatsapp_cost_beyond_the_free_tier(isolated_data, monkeypatch):
    _seed()
    monkeypatch.setattr(config, "WA_FREE_SERVICE_MESSAGES", 0)
    monkeypatch.setattr(config, "WA_UTILITY_RATE", 0.5)
    table = section(report.build_report(7, offline=OFFLINE), "## Estimated WhatsApp cost")
    assert cells(table, "Billable service messages")[1] == "11"
    assert cells(table, "**Estimated cost**")[1] == "US$ 6.50"  # (11 + 2) x 0.5
    assert cells(table, "Estimated cost per WhatsApp conversation")[1] == "US$ 3.2500"


# --- §1 targets ------------------------------------------------------------------------


def _target(text, metric):
    """(measured, by channel, target, status) of a §1 target row."""
    for line in text.splitlines():
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(parts) == 6 and parts[1] == metric:
            return parts[2:]
    raise AssertionError(metric)


def test_status_logic():
    assert report.status(None, ">=", 1.0) == report.NA
    assert report.status(0.95, ">=", 0.95) == report.PASS
    assert report.status(0.949, ">=", 0.95) == report.FAIL
    assert report.status(0.02, "<=", 0.02) == report.PASS
    assert report.status(0.021, "<=", 0.02) == report.FAIL
    assert report.status(0, "<=", 0) == report.PASS


def test_targets_pass_and_fail(seeded):
    rows = {
        "Red-team fraud, theft and lost-card reports caught by the urgent scan": ("100.0% (109/109)", "PASS"),
        "Red-team everyday messages sent straight into a report, without asking": ("0 of 49", "PASS"),
        "BANKING77 fraud and lost-card phrasings caught (CI gate)": ("75.0%", "FAIL"),
        "Out-of-scope questions answered directly (held-out set)": ("5.0%", "FAIL"),
        "In-scope questions answered right and directly": ("90.0%", "PASS"),
        "In-scope questions right or one tap away": ("95.0%", "PASS"),
        "Questions answered wrongly and confidently": ("2.0%", "PASS"),
        "Strikes per conversation": ("0.40", "n/a"),
        "Handoff SLA met": ("—", "n/a (needs H2)"),
        "CSAT (thumbs-up share × 5)": ("3.33 (2 of 3 thumbs up)", "FAIL"),
        "Delivery failures (WhatsApp, Messenger)": ("23.1%", "FAIL"),
        "Bot messages per conversation": ("7.00", "FAIL"),
    }
    for metric, (measured, expected) in rows.items():
        got = _target(seeded, metric)
        assert (got[0], got[3]) == (measured, expected), (metric, got)
    assert _target(seeded, "CSAT (thumbs-up share × 5)")[1] == "web 5.00 · whatsapp 2.50"
    assert _target(seeded, "Delivery failures (WhatsApp, Messenger)")[1] == "whatsapp 18.2% · messenger 50.0%"
    assert _target(seeded, "Bot messages per conversation")[1] == "web 11.00 · whatsapp 5.50 · messenger 2.00"
    assert "Launch targets: 5 met, 5 not met, 2 without data" in seeded


def test_targets_are_na_without_data(isolated_data):
    text = report.build_report(7, run_offline=False)
    for metric in ("In-scope questions answered right and directly", "CSAT (thumbs-up share × 5)",
                   "Delivery failures (WhatsApp, Messenger)", "Bot messages per conversation"):
        assert _target(text, metric)[3] == "n/a", metric
    assert "Launch targets: 0 met, 0 not met, 12 without data" in text
    assert "evaluation was skipped" in text


def test_offline_numbers_are_measured_when_not_given(isolated_data, monkeypatch):
    monkeypatch.setattr(report, "offline_metrics", lambda: dict(OFFLINE, right_direct=0.5))
    text = report.build_report(7)
    assert _target(text, "In-scope questions answered right and directly")[0] == "50.0%"


def test_redteam_metrics_on_the_real_corpora():
    m = report.redteam_metrics()
    assert m["redteam_n"] >= 60 and m["redteam_recall"] == 1.0  # the S1 suite enforces both
    assert m["redteam_hard_false"] == 0


# --- lead generation ------------------------------------------------------------------


def test_lead_section(seeded):
    lead = section(seeded, "## Lead generation (for Marketing)")
    assert cells(lead, "web") == ["2"] and cells(lead, "whatsapp") == ["2"]
    assert cells(lead, "messenger") == ["0"] and cells(lead, "**All**") == ["4"]
    topics = section(seeded, "### By topic")
    assert cells(topics, "Loans") == ["2"] and cells(topics, "Accounts") == ["1"]
    typed = section(seeded, "### Topics as typed (masked)")
    assert cells(typed, "a loan") == ["2"] and cells(typed, "opening a business account") == ["1"]
    assert "1 withheld because they looked personal" in typed
    sources = section(seeded, "### By campaign source")
    assert cells(sources, "qr_branch_cairo") == ["2"]
    assert cells(sources, "facebook_ad") == ["1"] and cells(sources, "unknown") == ["1"]
    consent = section(seeded, "### Marketing consent")
    assert cells(consent, "yes") == ["1"] and cells(consent, "no") == ["1"]
    assert cells(consent, "not asked") == ["1"] and cells(consent, "unknown") == ["1"]
    assert "Share of callbacks with marketing consent: 25.0%" in consent


@pytest.mark.parametrize("value", [True, "true", "yes", "YES", " yes", "sure", "ok", "yes please", "👍"])
def test_anything_that_means_yes_counts_as_consent(value):
    # D16: the report reads a stored value the way the flow reads a reply.
    assert report._consent({"marketing_consent": value}) == "yes"


@pytest.mark.parametrize("value, expected", [
    (False, "no"), ("no", "no"), ("not_asked", "not asked"), ("maybe", "unknown"),
    ("ok but no offers", "unknown"), (1, "unknown"), (None, "unknown"),
])
def test_everything_else_is_counted_as_it_reads(value, expected):
    assert report._consent({"marketing_consent": value}) == expected


def test_lead_section_without_source_or_consent_fields(isolated_data):
    audit.init_db()
    _ticket("callback", "web", {"name": "Mary", "phone": "0977123456", "topic": "a loan"})
    text = report.build_report(7, offline=OFFLINE)
    assert cells(section(text, "### By campaign source"), "unknown") == ["1"]
    assert "Not recorded on any callback" in section(text, "### Marketing consent")


def test_no_callbacks(isolated_data):
    text = report.build_report(7, offline=OFFLINE)
    assert "No callback requests in this window." in text


# --- privacy and safety ----------------------------------------------------------------


def test_no_raw_id_or_personal_detail_appears(seeded):
    for sid, _, uh in SESSIONS.values():
        assert sid not in seeded and uh not in seeded
    assert "sess-old" not in seeded and "uhdeliveryhash01" not in seeded
    for value in PERSONAL:
        assert value not in seeded, value


def test_top_unmatched_is_kept_and_checked_twice(seeded):
    unmatched = section(seeded, "## Top unmatched utterances")
    assert cells(unmatched, "flurb") == ["1"] and cells(unmatched, "zzz qqq") == ["1"]
    assert "1 withheld because they looked personal" in unmatched


def test_free_text_cannot_inject_markup(isolated_data):
    s = Seed("W1")
    s.user("x").system("unmatched", '"><img src=x onerror=alert(1)> | pipe').bot("fallback")
    text = report.build_report(7, offline=OFFLINE)
    assert "<img" not in text
    assert "&lt;img src=x onerror=alert(1)&gt; \\| pipe" in text


# --- the new audit actions, logged by the real code -------------------------------------


def test_correction_is_logged_without_the_value(bot):
    b = bot()
    b.tap("human_handoff")
    b.say("Mary")
    b.say("0977123456")
    b.say("a loan")
    b.say("sorry my number is actually 0966123456")
    assert b.session.flow_state["data"]["phone"] == "0966123456"
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute("SELECT text, channel, user_hash FROM events WHERE action = 'correction'").fetchall()
    con.close()
    assert rows == [("correction: lead.phone", "web", b.session.user_hash)]


def test_two_answers_are_logged_as_multi_answer(bot):
    b = bot()
    b.say("what are your opening hours and where is the kitwe branch")
    assert len(b.last[1]["intents"]) == 2
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute("SELECT text, intent FROM events WHERE action = 'multi_answer'").fetchall()
    con.close()
    assert len(rows) == 1 and rows[0][0].startswith("multi_answer: ")


def test_real_conversations_reach_the_report(bot, monkeypatch):
    monkeypatch.setenv("CSAT_SAMPLE_RATE", "1")
    b = bot(channel="whatsapp")
    b.say("what is etumba")
    b.say("thanks")
    b.tap("csat:up")
    b = bot()
    b.say("what are your opening hours and where is the kitwe branch")
    text = report.build_report(7, offline=OFFLINE)
    assert channel_row(text, "CSAT thumbs up") == ["1", "0", "1", "0"]
    assert channel_row(text, "CSAT asked") == ["1", "0", "1", "0"]
    assert channel_row(text, "Two questions answered in one reply") == ["1", "1", "0", "0"]
    assert b.session.user_hash not in text and b.session.id not in text


# --- CLI ---------------------------------------------------------------------------------


def test_cli_writes_data_report_md_by_default(isolated_data, capsys):
    report.main(["--days", "7", "--skip-eval"])
    out = isolated_data / "report.md"
    assert out.exists() and out.read_text(encoding="utf-8").startswith("# Chatbot weekly quality report")
    assert "written:" in capsys.readouterr().out


def test_cli_out_and_stdout(isolated_data, tmp_path, capsys):
    target = tmp_path / "custom.md"
    report.main(["--days", "3", "--skip-eval", "--out", str(target)])
    assert "last 3 days" in target.read_text(encoding="utf-8")
    report.main(["--skip-eval", "--stdout"])
    assert "## Launch targets" in capsys.readouterr().out
