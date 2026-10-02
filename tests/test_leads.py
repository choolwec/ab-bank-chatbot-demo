"""Lead capture per the team's flow document (V1/2026): product pages end in
"Yes, contact me", and the callback form never asks what it is about -- the
ticket's topic is the product, and every product viewed goes with it."""
import json
import sqlite3

import pytest

from app import audit
from app.router import MENU_BUTTONS, matcher


def _tickets():
    con = sqlite3.connect(audit.DB_FILE)
    rows = con.execute("SELECT type, fields FROM tickets ORDER BY id").fetchall()
    con.close()
    return [(kind, json.loads(fields)) for kind, fields in rows]


def _finish(b):
    b.say("Mary Banda")
    b.say("0977123456")
    assert "when is best to call" in b.text.lower()  # straight to the time
    b.tap("time:Anytime")
    b.tap("marketing_consent:no")
    b.tap("confirm_yes")
    assert "will contact you shortly" in b.text or "will contact you" in b.text


def test_main_menu_follows_the_flow_document():
    assert [b["payload"] for b in MENU_BUTTONS] == [
        "account_types_overview", "loans_overview", "invest_overview",
        "digital_banking", "branch_locator", "complaints_feedback", "human_handoff",
    ]
    for b in MENU_BUTTONS[:-1]:
        assert matcher.get(b["payload"]), b
        assert len(b["label"]) <= 20


def test_welcome_says_automated_assistant_only(client):
    text = client.post("/chat", json={}).json()["replies"][0]["text"]
    assert "automated assistant" in text and "not a person" not in text


def test_yes_contact_me_on_a_product_skips_the_topic(bot, isolated_data):
    b = bot()
    b.tap("savings_options")
    b.tap("savings_plan_account")
    assert b.buttons[0] == "lead:savings_plan_account"
    b.tap("lead:savings_plan_account")
    assert b.session.active_flow == "lead"
    assert "Savings Plan" in b.text and "full name" in b.text
    _finish(b)
    (kind, fields), = _tickets()
    assert kind == "callback"
    assert fields["topic"] == "Savings Plan"
    assert fields["interests"] == "Savings Plan"
    assert fields["time"] == "Anytime"


def test_talk_to_an_agent_carries_what_they_looked_at(bot, isolated_data):
    b = bot()
    b.tap("trader_mobility_loan")
    b.tap("term_deposit_account")
    b.tap("human_handoff")
    assert "Contact Centre representative will get in touch" in b.text
    _finish(b)
    (_, fields), = _tickets()
    assert fields["topic"] == "Term Deposit"  # the last product viewed
    assert fields["interests"] == "Trader Mobility Loan, Term Deposit"


def test_no_products_viewed_is_a_general_enquiry(bot, isolated_data):
    b = bot()
    b.say("how are you")
    b.tap("human_handoff")
    _finish(b)
    (_, fields), = _tickets()
    assert fields["topic"] == "General enquiry"
    assert "interests" not in fields


def test_typed_yes_on_a_product_starts_the_lead(bot):
    b = bot()
    b.tap("micro_loan")
    b.say("yes")
    assert b.session.active_flow == "lead"
    assert b.last[1]["interest"] == "micro_loan"


def test_back_returns_to_the_parent_menu(bot):
    b = bot()
    b.tap("sme_loan")
    assert "business_loan_options" in b.buttons
    b.tap("business_loan_options")
    assert {"trader_mobility_loan", "micro_loan", "sme_loan"} <= set(b.buttons)


@pytest.mark.parametrize("name", sorted(n for n, i in matcher.intents.items() if i.get("lead_topic")))
def test_every_product_has_a_lead_topic_and_a_way_to_a_lead(bot, name):
    b = bot()
    b.tap(name)
    assert any(p.startswith("lead:") or p in ("human_handoff", "request_callback") for p in b.buttons), name
    assert len(matcher.get(name)["lead_topic"]) <= 40


def test_clear_chat_forgets_the_interests(bot):
    b = bot()
    b.tap("micro_loan")
    b.say("clear chat")
    assert "interests" not in b.session.slots


def test_jira_summary_names_the_product(bot, isolated_data, monkeypatch):
    from app import config, jira_export

    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: False)
    b = bot()
    b.tap("online_banking")
    b.tap("lead:online_banking")
    _finish(b)
    lines = (isolated_data / "jira_mock.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert "Internet Banking registration" in json.loads(lines[-1])["summary"]
    assert jira_export  # imported for the mock path


# --- A direct question moves to what the customer wants -------------------------

@pytest.mark.parametrize("steps", [
    [],                                              # the name step
    ["Mary Banda"],                                  # the phone step
    ["Mary Banda", "0977123456"],                    # the time step
])
@pytest.mark.parametrize("question", ["where is the kitwe branch", "kitwe branch"])
def test_branch_question_inside_the_callback_form_is_answered(bot, steps, question):
    b = bot()
    b.tap("human_handoff")
    for s in steps:
        b.say(s)
    before = dict(b.session.flow_state["data"])
    b.say(question)
    assert b.action == "digression:lead"
    assert "Kitwe Branch" in b.text and "Chisokone" in b.text
    assert b.session.flow_state["data"] == before  # nothing stored as a name or time
    assert b.session.active_flow == "lead"


def test_agent_question_inside_the_callback_form_is_answered(bot):
    b = bot()
    b.tap("human_handoff")
    b.say("where can i find an agent")
    assert b.action == "digression:lead" and "Kazang" in b.text
    assert "name" not in b.session.flow_state["data"]


@pytest.mark.parametrize("opener", ["someone stole my card", "I want to complain"])
def test_branch_question_inside_a_report_is_answered_and_the_report_kept(bot, opener):
    b = bot()
    b.say(opener)
    flow = b.session.active_flow
    b.say("where is the kitwe branch?")
    assert b.action == f"digression:{flow}" and "Kitwe Branch" in b.text
    assert b.session.active_flow == flow


def test_a_branch_in_the_fraud_story_stays_part_of_the_story(bot):
    b = bot()
    b.say("someone stole my card")
    b.say("it happened at the kitwe branch")
    assert b.session.flow_state["data"]["what_happened"] == "it happened at the kitwe branch"


@pytest.mark.parametrize("typed", ["where is the kitwe branch", "kitwe", "is there a branch in ndola?"])
def test_branch_finder_reads_the_town_from_a_sentence(bot, typed):
    b = bot()
    b.tap("branch_locator")
    b.say(typed)
    assert "Here's what I found" in b.text, b.text
    assert b.session.active_flow is None


def test_the_documents_wording_is_used_in_full():
    assert matcher.get("micro_loan")["answer_short"].startswith("Need financing to support your small business?")
    assert "K1,000 to K350,000" in matcher.get("micro_loan")["answer"]  # the researched details
    assert "K300,000 per day" in matcher.get("online_banking")["answer"]
    assert matcher.get("savings_plan_account")["answer_short"].endswith("Ready to start saving towards your goal?")
