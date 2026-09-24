"""Regression suite over the intent knowledge base (acceptance §3.5).

Every phrase in every intent must reach its own intent. Content edits are
deploys — this suite gates them (§6).
"""

import pytest

from app import config
from app.router import matcher


def test_launch_intent_count():
    assert len(matcher.intents) >= 25


def test_every_intent_has_label_and_answer_or_flow():
    for name, intent in matcher.intents.items():
        assert intent.get("label"), name
        assert intent.get("answer") or intent.get("flow"), name


def test_every_answer_has_buttons():
    # No dead ends is also enforced at runtime; this catches it at edit time.
    for name, intent in matcher.intents.items():
        if intent.get("answer"):
            assert intent.get("buttons"), f"{name} has an answer but no buttons"


def test_canonical_phrase_is_top1():
    for name, intent in matcher.intents.items():
        canonical = intent["phrases"][0]
        ranked = matcher.match(canonical)
        assert ranked and ranked[0][0] == name, (
            f"{name}: canonical '{canonical}' -> {ranked[:3]}"
        )


def test_all_phrases_reach_their_intent():
    failures = []
    for name, intent in matcher.intents.items():
        for phrase in intent["phrases"]:
            ranked = matcher.match(phrase)[:3]
            ok = any(n == name and s >= config.MEDIUM_CONFIDENCE for n, s in ranked)
            if not ok:
                failures.append((name, phrase, ranked))
    assert not failures, failures


@pytest.mark.parametrize(
    "query,expected",
    [
        ("wat is etumba", "etumba_what_is"),
        ("compliant", "complaint"),
        ("i want loan", "loan_apply_how"),
        ("requirements for opening acount", "account_opening_requirements"),
        ("stollen card", "lost_stolen_card"),
        ("savngs account", "savings_account"),
        ("hie", "greeting"),
        ("the app is not working", "technical_issue"),
        ("myabz is down", "technical_issue"),
        ("etumba is down", "technical_issue"),
        ("mymbs is down", "technical_issue"),
        ("no", "thanks_goodbye"),
        ("nope", "thanks_goodbye"),
        ("nothing else", "thanks_goodbye"),
        ("i'm done", "thanks_goodbye"),
        # Added 2026-07-25 after reviewing external banking-chatbot repos for
        # V1 improvement ideas: several (the Dialogflow and Rasa demos) hit
        # near-miss confusions in exactly this style — a close cousin to the
        # already-fixed credential_trouble/technical_issue misroute.
        # Note: "cant log in" phrasing is deliberately credential_trouble
        # (PIN-reset flow), not technical_issue — see knowledge/intents/
        # urgent.yaml's "cant log in to myabz" phrase. Login-failure wording
        # is genuinely ambiguous (forgotten PIN vs. outage); these cases stay
        # on the outage side by describing a crash/error rather than a login.
        ("network error on the app", "technical_issue"),
        ("the etumba app keeps crashing", "technical_issue"),
        ("how do i open a savings acc", "savings_account"),
        ("wat do i need to open an account", "account_opening_requirements"),
        ("do you guys do loans for small business", "msme_loan"),
        ("were is the nearest branch", "branch_locator"),
        ("i wana talk to somone", "human_handoff"),
        ("can i speak to a human", "human_handoff"),
        ("someone stole money from my account", "fraud_scam"),
        ("i think someone hacked into my etumba", "fraud_scam"),
        ("wats ur workin hours", "opening_hours"),
        ("how much do you charge for a savings account", "fees_charges"),
    ],
)
def test_misspellings_and_zambian_english(query, expected):
    ranked = matcher.match(query)[:3]
    assert any(n == expected for n, _ in ranked), (query, ranked)


def test_gibberish_scores_low():
    ranked = matcher.match("flurb zzqx vortblatt")
    assert not ranked or ranked[0][1] < config.MEDIUM_CONFIDENCE


def test_answer_simple_is_plainer_and_present_for_top_intents():
    """C4/K1: 'what do you mean?' has a legally reviewable plainer version
    for at least the 15 most-used intents, and it really is shorter."""
    simple = {n: i for n, i in matcher.intents.items() if i.get("answer_simple")}
    assert len(simple) >= 15, sorted(simple)
    for name, intent in simple.items():
        assert intent.get("answer"), name
        assert len(intent["answer_simple"]) < len(intent["answer"]), name
        assert "[CONFIRM" not in intent["answer_simple"], name


def test_follow_ups_point_at_real_intents():
    """C9: follow_ups maps {generic intent: specific intent}, both real."""
    for name, intent in matcher.intents.items():
        for generic, specific in (intent.get("follow_ups") or {}).items():
            assert generic in matcher.intents, (name, generic)
            assert specific in matcher.intents, (name, specific)


def test_every_long_label_has_a_short_label():
    """K1: WhatsApp buttons allow 20 characters. Every intent label and YAML
    button label longer than that carries a short_label that fits."""
    missing = []
    for name, intent in matcher.intents.items():
        items = [intent] + list(intent.get("buttons", []))
        for item in items:
            if len(item["label"]) > 20:
                short = item.get("short_label", "")
                if not short or len(short) > 20:
                    missing.append((name, item["label"], short))
    assert not missing, missing



@pytest.mark.parametrize(
    "query",
    ["where is the passport office", "how do i pay my zra tax", "my zesco power is off",
     "what is the kwacha exchange rate"],
)
def test_other_organisations_services_get_the_out_of_scope_answer(query):
    """N6: hard lookalikes get "that's not something I can help with"."""
    ranked = matcher.match(query)
    assert ranked[0][0] == "out_of_scope", (query, ranked[:3])


# --- Negation (hybrid switch-over prep, 2026-09-24) -----------------------------


@pytest.mark.parametrize(
    "text,kept",
    [
        ("I don't want a loan, I want to open an account", "I want to open an account"),
        ("I want to open an account instead of a loan", "I want to open an account"),
        ("i dont need a new card but where is the kitwe branch", "where is the kitwe branch"),
        ("no, i want a business loan", "i want a business loan"),
        ("im not interested in etumba, tell me about tamanga", "tell me about tamanga"),
        ("I don't want a loan and I want to open an account", "I want to open an account"),
        ("not a savings account, a current account please", "a current account please"),
    ],
)
def test_negated_clause_is_dropped_before_scoring(text, kept):
    from app.matcher import drop_negated_clauses

    assert drop_negated_clauses(text) == kept


@pytest.mark.parametrize(
    "text",
    [
        "my card is not working, what do i do",   # a problem report, not a negated request
        "i don't have an nrc",                     # one clause: nothing to fall back on
        "i dont want a loan",                      # everything negated: score as it is
        "i don't want it, cancel",                 # what is left is under 3 words
        "i need a loan but i don't have collateral",
        "why don't you want to give me a loan, my business is good",
        # past tense describes what happened: the topic must stay
        "i didn't want insurance but they charged me, how do i cancel it",
        "I didn't mean to send money to the wrong number, how do I reverse it",
        "i did not need this debit order, please reverse it",
        # "not sure" is a question, not a ruled-out topic
        "not sure which account to open, can you help me choose",
    ],
)
def test_text_without_a_droppable_negated_clause_is_unchanged(text):
    from app.matcher import drop_negated_clauses

    assert drop_negated_clauses(text) == text


def test_negated_topic_no_longer_steers_the_character_matcher():
    ranked = matcher.match("I don't want a loan, I want to open an account")
    assert ranked[0] == ("account_opening_how", 1.0)
    ranked = matcher.match("not a business loan, i need a personal loan")
    assert ranked[0][0] == "personal_loan", ranked[:3]


def test_negated_and_clause_is_one_question_not_two(bot):
    b = bot()
    b.say("I don't want a loan and I want to open an account")
    assert b.action == "answer"
    assert b.last[1]["intent"] == "account_opening_how"
    assert "intents" not in b.last[1]  # not a C10 double answer with the loan
