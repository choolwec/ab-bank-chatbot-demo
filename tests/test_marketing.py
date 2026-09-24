"""Marketing and lead generation: consent (MK2), opt-out, campaign source
(MK3), the "Continue on WhatsApp" link (W10) and callback reach from every
product answer. All network is mocked (Jira runs in mock mode)."""

import json
import sqlite3
import time
from pathlib import Path

import pytest
import yaml

from app import audit, campaign, config, jira_export
from app.router import matcher

from conftest import chat

WA = Path(__file__).parent / "data" / "wa"
HUMAN = "human_handoff"


def _to_summary(b, consent=None):
    b.tap(HUMAN)
    b.say("Mary Banda")
    b.say("0977123456")
    b.say("a loan")
    b.tap("time:Morning")
    if consent:
        b.tap(f"marketing_consent:{consent}")


def _tickets():
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute("SELECT type, fields FROM tickets ORDER BY id").fetchall()
    con.close()
    return [(kind, json.loads(fields)) for kind, fields in rows]


def _events(action):
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute(
        "SELECT text, user_hash, channel FROM events WHERE action = ? ORDER BY id", (action,)
    ).fetchall()
    con.close()
    return rows


@pytest.fixture
def jira_mock(monkeypatch, isolated_data):
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: False)
    return isolated_data


# --- MK2: the consent question ------------------------------------------------


def test_consent_is_asked_after_time_with_the_opt_out_stated(bot):
    b = bot()
    _to_summary(b)
    assert "news and offers" in b.text
    assert "unsubscribe" in b.text  # how to stop, stated up front
    assert "goes ahead either way" in b.text  # not a condition of the callback
    assert b.buttons == ["marketing_consent:yes", "marketing_consent:no", "cancel_flow"]
    assert b.session.flow_state["step"] == 4


def test_consent_yes_is_stored_with_a_timestamp_and_shown_in_the_summary(bot):
    b = bot()
    _to_summary(b, consent="yes")
    data = b.session.flow_state["data"]
    assert data["marketing_consent"] == "yes"
    assert data["marketing_consent_at"].endswith("+00:00")
    assert "Mary Banda · 0977 123 456 · a loan · Morning · News and offers: yes" in b.text


@pytest.mark.parametrize("typed, stored", [("yes", "yes"), ("no", "no"), ("I agree", "yes"), ("no thanks", "no")])
def test_consent_can_be_typed(bot, typed, stored):
    b = bot()
    _to_summary(b)
    b.say(typed)
    assert b.session.flow_state["data"]["marketing_consent"] == stored
    assert "shall i send it" in b.text.lower()


def test_an_unclear_consent_answer_is_asked_again(bot):
    b = bot()
    _to_summary(b)
    b.say("maybe later")
    assert "marketing_consent" not in b.session.flow_state["data"]
    assert "tap yes or no" in b.text.lower()


def test_an_unclear_consent_answer_keeps_the_yes_no_buttons(bot):
    b = bot()
    _to_summary(b)
    b.say("maybe later")
    assert b.buttons == ["marketing_consent:yes", "marketing_consent:no", "cancel_flow"]
    b.say("yes")
    assert b.session.flow_state["data"]["marketing_consent"] == "yes"


def test_after_an_opt_out_consent_cannot_be_changed_back(bot):
    b = bot()
    _to_summary(b, consent="yes")
    b.say("unsubscribe")
    b.tap("confirm_change")
    assert "change:marketing_consent" not in b.buttons
    b.tap("change:marketing_consent")  # an old button is not honoured either
    b.tap("marketing_consent:yes")
    assert b.session.flow_state["data"]["marketing_consent"] == "no"


def test_opting_out_while_changing_consent_never_records_yes(bot, isolated_data):
    b = bot()
    _to_summary(b, consent="yes")
    b.tap("confirm_change")
    b.tap("change:marketing_consent")
    b.say("unsubscribe")
    assert "shall i send it" in b.text.lower()
    assert "news and offers from ab bank?" not in b.text.lower()
    b.say("yes")  # the summary's yes: send it
    assert _tickets()[-1][1]["marketing_consent"] == "no"


def test_consent_can_be_changed_from_the_summary(bot):
    b = bot()
    _to_summary(b, consent="yes")
    first_at = b.session.flow_state["data"]["marketing_consent_at"]
    b.tap("confirm_change")
    assert "change:marketing_consent" in b.buttons
    b.tap("change:marketing_consent")
    assert "news and offers" in b.text
    b.tap("marketing_consent:no")  # the self-describing id is understood when editing too
    data = b.session.flow_state["data"]
    assert data["marketing_consent"] == "no"
    assert data["marketing_consent_at"] >= first_at
    assert "News and offers: no" in b.text


def test_consent_yes_reaches_the_ticket_and_the_jira_label(bot, jira_mock):
    b = bot()
    _to_summary(b, consent="yes")
    b.tap("confirm_yes")
    kind, fields = _tickets()[-1]
    assert kind == "callback"
    assert fields["marketing_consent"] == "yes" and fields["marketing_consent_at"]
    issue = jira_export.read_mock_issues()[0]
    assert jira_export.CONSENT_LABEL in issue["labels"]
    assert "- marketing_consent: yes" in issue["description"]


def test_consent_no_gets_no_marketing_label(bot, jira_mock):
    b = bot()
    _to_summary(b, consent="no")
    b.tap("confirm_yes")
    issue = jira_export.read_mock_issues()[0]
    assert jira_export.CONSENT_LABEL not in issue["labels"]
    assert "- marketing_consent: no" in issue["description"]


def test_flag_off_skips_the_question_and_says_not_asked(bot, jira_mock, monkeypatch):
    monkeypatch.setenv("MARKETING_CONSENT_ENABLED", "false")
    b = bot()
    _to_summary(b)
    assert "shall i send it" in b.text.lower()
    assert "news and offers" not in b.text.lower()
    b.tap("confirm_change")
    assert "change:marketing_consent" not in b.buttons
    b.tap("confirm_yes")
    assert _tickets()[-1][1]["marketing_consent"] == "not_asked"
    assert jira_export.CONSENT_LABEL not in jira_export.read_mock_issues()[0]["labels"]


def test_flag_turned_off_mid_question_moves_on_to_the_summary(bot, monkeypatch):
    b = bot()
    _to_summary(b)
    monkeypatch.setenv("MARKETING_CONSENT_ENABLED", "false")
    b.say("repeat")  # repeat resends the old reply; a page reload resumes
    replies, _ = b.router.resume(b.session)
    assert "shall i send it" in replies[-1]["text"].lower()


def test_the_consent_question_is_not_a_correction_target(bot):
    b = bot()
    _to_summary(b, consent="yes")
    b.say("actually my number is 0966 123 456")
    assert b.session.flow_state["data"]["phone"] == "0966123456"
    assert b.session.flow_state["data"]["marketing_consent"] == "yes"


# --- MK2: opting out ----------------------------------------------------------------


@pytest.mark.parametrize("text", ["unsubscribe", "Opt out", "opt-out", "STOP OFFERS", "stop marketing",
                                  "no more offers", "Unsubscribe please"])
def test_opt_out_commands_are_logged_with_the_user_hash(bot, text):
    b = bot()
    b.say(text)
    assert b.action == "marketing_opt_out"
    assert "news and offers" in b.text
    assert b.buttons  # no dead end
    events = _events("marketing_opt_out")
    assert events and events[-1][1] == b.session.user_hash
    assert b.session.slots["marketing_opt_out"]


def test_bare_stop_still_cancels(bot):
    b = bot()
    b.tap(HUMAN)
    b.say("Mary")
    b.say("stop")
    assert b.action == "cancel"
    assert b.session.active_flow is None
    assert not _events("marketing_opt_out")
    assert "marketing_opt_out" not in b.session.slots


def test_cancel_my_card_is_still_a_card_report(bot):
    b = bot()
    b.say("unsubscribe my card")  # not a whole-message command
    assert b.action != "marketing_opt_out"


def test_opted_out_customers_are_never_asked(bot, isolated_data):
    b = bot()
    b.say("unsubscribe")
    _to_summary(b)
    assert "shall i send it" in b.text.lower()
    assert "marketing_consent" not in b.session.flow_state["data"]
    b.tap("confirm_yes")
    fields = _tickets()[-1][1]
    assert fields["marketing_consent"] == "no"
    assert fields["marketing_consent_at"] == b.session.slots["marketing_opt_out"]


def test_opting_out_at_the_consent_question_moves_on_to_the_summary(bot):
    b = bot()
    _to_summary(b)
    b.say("unsubscribe")
    assert b.action == "marketing_opt_out"
    assert b.session.flow_state["data"]["marketing_consent"] == "no"
    assert "shall i send it" in b.text.lower()
    assert b.session.active_flow == "lead"  # the callback is not dropped


def test_opting_out_after_saying_yes_overrides_it(bot):
    b = bot()
    _to_summary(b, consent="yes")
    b.say("stop offers")
    assert b.session.flow_state["data"]["marketing_consent"] == "no"
    assert "News and offers: no" in b.text


def test_opting_out_mid_fraud_report_keeps_the_report(bot):
    b = bot()
    b.say("my card was stolen")
    step = b.session.flow_state["step"]
    b.say("unsubscribe")
    assert b.session.active_flow == "fraud" and b.session.flow_state["step"] == step


# --- MK3: campaign source ---------------------------------------------------------------


@pytest.mark.parametrize("raw, clean", [
    ("CAIRO01", "cairo01"),
    ("spring sale!", "springsale"),
    ("fb_2026-oct", "fb_2026-oct"),
    ("<script>alert(1)</script>", "scriptalert1script"),
    ("x" * 60, "x" * 40),
    ("!!!", None),
    ("", None),
    (None, None),
    ("0977123456", None),  # looks like a phone number: never stored
])
def test_sanitise(raw, clean):
    assert campaign.sanitise(raw) == clean


def test_extract_strips_every_token():
    assert campaign.extract("Hi ref:CAIRO01") == ("cairo01", "Hi")
    assert campaign.extract("ref:qr-lusaka what is etumba") == ("qr-lusaka", "what is etumba")
    assert campaign.extract("what is etumba") == (None, "what is etumba")
    assert campaign.extract("my ref:A and ref:B") == ("a", "my and")
    assert campaign.extract("preference:x") == (None, "preference:x")  # whole token only


def test_web_source_is_stored_on_the_session_and_logged_once(client, isolated_data):
    first = client.post("/chat", json={"source": "Spring Sale!"}).json()
    sid = first["session_id"]
    from app.session import store

    with store.web_session(sid) as (session, _):
        assert session.slots["source"] == "springsale"
    client.post("/chat", json={"session_id": sid, "message": "hi", "source": "other"})
    with store.web_session(sid) as (session, _):
        assert session.slots["source"] == "springsale"  # first touch wins
    events = _events("session_source")
    assert [e[0] for e in events] == ["source: springsale"]


def test_web_source_reaches_the_callback_ticket_and_jira(client, jira_mock):
    sid = client.post("/chat", json={"source": "cairo01"}).json()["session_id"]
    for kw in ({"payload": HUMAN}, {"message": "Mary"}, {"message": "0977123456"},
               {"message": "a loan"}, {"payload": "time:Morning"}, {"payload": "marketing_consent:no"},
               {"payload": "confirm_yes"}):
        chat(client, sid, **kw)
    assert _tickets()[-1][1]["source"] == "cairo01"
    assert "- source: cairo01" in jira_export.read_mock_issues()[0]["description"]


def test_callback_source_defaults_to_unknown(bot, isolated_data):
    b = bot()
    _to_summary(b, consent="no")
    b.tap("confirm_yes")
    assert _tickets()[-1][1]["source"] == "unknown"


def test_a_pii_looking_source_is_dropped(client, isolated_data):
    sid = client.post("/chat", json={"source": "0977123456"}).json()["session_id"]
    from app.session import store

    with store.web_session(sid) as (session, _):
        assert "source" not in session.slots
    assert not _events("session_source")


def _wa_say(meta_env, text):
    body = json.loads((WA / "text.json").read_text(encoding="utf-8").replace("TS", str(int(time.time()))))
    m = body["entry"][0]["changes"][0]["value"]["messages"][0]
    m["text"] = {"body": text}
    m["id"] = f"wamid.{time.time_ns()}"
    assert meta_env.post("whatsapp", body).status_code == 200
    meta_env.process()


def test_whatsapp_token_is_recorded_and_stripped_before_matching(meta_env):
    _wa_say(meta_env, "what is etumba ref:CAIRO01")
    assert any("mobile wallet" in t for t in meta_env.sent_texts("whatsapp"))
    assert [e[0] for e in _events("session_source")] == ["source: cairo01"]
    con = sqlite3.connect(audit.DB_FILE)
    user_texts = [r[0] for r in con.execute("SELECT text FROM events WHERE role='user'")]
    con.close()
    assert user_texts == ["what is etumba"]  # the token never reaches the log or matcher
    assert all("260977123456" not in (e[1] or "") for e in _events("session_source"))


def test_whatsapp_token_alone_is_a_greeting(meta_env):
    _wa_say(meta_env, "ref:qr-lusaka")
    texts = meta_env.sent_texts("whatsapp")
    assert any("automated helper" in t for t in texts)
    assert not any("didn't quite catch" in t for t in texts)


def test_whatsapp_source_reaches_the_callback_ticket(meta_env):
    for text in ["Hi ref:cairo01", "talk to a person", "Mary", "0977123456", "a loan", "morning", "no", "yes"]:
        _wa_say(meta_env, text)
    kind, fields = _tickets()[-1]
    assert kind == "callback" and fields["source"] == "cairo01"


# --- W10: "Continue on WhatsApp" ------------------------------------------------------------


def test_health_hides_the_whatsapp_link_by_default(client, monkeypatch):
    monkeypatch.delenv("WA_LINK_ENABLED", raising=False)
    health = client.get("/health").json()
    assert health["wa_link_enabled"] is False and health["wa_link"] is None


def test_health_exposes_the_whatsapp_link_when_enabled(client, monkeypatch):
    monkeypatch.setenv("WA_LINK_ENABLED", "true")
    health = client.get("/health").json()
    assert health["wa_link_enabled"] is True
    assert health["wa_link"] == "https://wa.me/260769651262"


def test_widget_link_carries_a_campaign_token_and_no_session_data():
    js = (Path(__file__).parent.parent / "widget" / "widget.js").read_text(encoding="utf-8")
    assert "wa_link_enabled" in js and "Continue on WhatsApp" in js
    assert '"Hi ref:"' in js
    start = js.index("function waHref")
    body = js[start: js.index("}", start)]
    assert "sessionId" not in body  # nothing about the conversation in the URL
    assert 'rel: "noopener noreferrer"' in js
    assert "data-campaign" in js and "utm_campaign" in js and "utm_source" in js


# --- Lead capture coverage --------------------------------------------------------------------

PRODUCT_CATEGORIES = {"accounts", "loans", "fees", "etumba"}


def test_every_product_answer_offers_a_callback_in_one_tap(bot):
    missing = []
    for name, intent in sorted(matcher.intents.items()):
        if intent.get("category") not in PRODUCT_CATEGORIES or intent.get("flow"):
            continue
        b = bot()
        b.tap(name)
        if HUMAN not in b.buttons:
            missing.append(name)
            continue
        b.tap(HUMAN)
        if b.session.active_flow != "lead":
            missing.append(name)
    assert not missing, f"product answers without a callback button: {missing}"


def test_intent_files_declare_the_callback_button():
    """The same rule, read straight from the content files."""
    root = Path(__file__).parent.parent / "knowledge" / "intents"
    for path in root.glob("*.yaml"):
        for intent in yaml.safe_load(path.read_text(encoding="utf-8"))["intents"]:
            if intent.get("category") in PRODUCT_CATEGORIES and not intent.get("flow"):
                payloads = [b["payload"] for b in intent.get("buttons", [])]
                assert HUMAN in payloads, intent["intent"]


# --- Measuring campaigns: the weekly report ---------------------------------------------------


def test_weekly_report_counts_campaigns_consent_and_opt_outs(client, isolated_data):
    from admin.report import build_report

    sid = client.post("/chat", json={"source": "cairo01"}).json()["session_id"]
    for kw in ({"payload": HUMAN}, {"message": "Mary"}, {"message": "0977123456"},
               {"message": "a loan"}, {"payload": "time:Morning"}, {"payload": "marketing_consent:yes"},
               {"payload": "confirm_yes"}):
        chat(client, sid, **kw)
    other = client.post("/chat", json={}).json()["session_id"]
    chat(client, other, message="unsubscribe")
    report = build_report(7)
    assert "Marketing opt-outs: 1" in report
    assert "| cairo01 | 1 | 1 | 1 |" in report
    assert "Mary" not in report and "0977123456" not in report  # counts only


def test_consent_wording_is_flagged_for_legal_in_the_export():
    from admin import legal_export

    doc = legal_export.build_doc()
    start = doc.index("### `lead.step.marketing_consent`")
    assert "For Legal:" in doc[start: start + 800] and "ECT Act 2021" in doc[start: start + 800]
