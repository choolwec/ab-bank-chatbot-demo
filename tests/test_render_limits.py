"""P3: every reply the bot can send fits every channel's limits.

A content edit that breaks a WhatsApp or Messenger limit fails CI here, the
same way a dead end fails test_no_dead_ends_for_every_intent.
"""

import pytest

from app import render
from app.router import matcher

HUMAN = "human_handoff"


def _replies_for_every_path(bot):
    """(name, reply) for every intent answer plus the system replies."""
    out = []
    for name in sorted(matcher.intents):
        b = bot()
        replies, _ = b.tap(name)
        out += [(f"intent:{name}", r) for r in replies]
    b = bot()
    out.append(("welcome", b.session.last_replies[-1]))
    for label, steps in {
        "did_you_mean": [("say", "loan")],
        "city_picker": [("tap", "branch_locator")],
        "urgent_confirm": [("say", "my money is gone")],
        "fraud_prefill": [("say", "I lost my card yesterday at cairo branch")],
        "summary": [("tap", "human_handoff"), ("say", "Mary"), ("say", "0977123456"),
                    ("say", "a loan"), ("tap", "time:Morning")],
        "change_menu": [("say", "I want to complain"), ("say", "a branch"), ("say", "slow service"),
                        ("say", "skip"), ("tap", "confirm_change")],
        "frustration": [("say", "this is not helping")],
        "two_answers": [("say", "what are your opening hours and where is the kitwe branch")],
    }.items():
        b = bot()
        for kind, value in steps:
            replies, _ = b.say(value) if kind == "say" else b.tap(value)
        out += [(label, r) for r in replies]
    return out


def _wa_titles(message):
    inter = message.get("interactive")
    if not inter:
        return []
    if inter["type"] == "button":
        return [(b["reply"]["title"], 20) for b in inter["action"]["buttons"]]
    return [(r["title"], 24) for s in inter["action"]["sections"] for r in s["rows"]]


def test_every_reply_fits_whatsapp(bot):
    problems = []
    for name, reply in _replies_for_every_path(bot):
        messages = render.whatsapp(reply)
        payloads = set()
        for m in messages:
            if m["type"] == "text":
                assert len(m["text"]["body"]) <= render.WA_TEXT_MAX, name
                continue
            inter = m["interactive"]
            assert len(inter["body"]["text"]) <= render.WA_BODY_MAX, name
            if inter["type"] == "button":
                assert 1 <= len(inter["action"]["buttons"]) <= render.WA_BUTTONS_MAX, name
                payloads |= {b["reply"]["id"] for b in inter["action"]["buttons"]}
            else:
                rows = [r for s in inter["action"]["sections"] for r in s["rows"]]
                assert 1 <= len(rows) <= render.WA_LIST_ROWS_MAX, name
                assert len(inter["action"]["button"]) <= render.WA_LIST_BUTTON_MAX
                for r in rows:
                    assert len(r.get("description", "")) <= render.WA_ROW_DESC_MAX, name
                    assert len(r["id"]) <= render.WA_ID_MAX
                payloads |= {r["id"] for r in rows}
            for title, limit in _wa_titles(m):
                if len(title) > limit or title.endswith("…") and title != "More…":
                    problems.append((name, title))
        if any(b["payload"] == HUMAN for b in reply["buttons"]):
            assert HUMAN in payloads, f"{name}: WhatsApp rendering dropped the human option"
    assert not problems, f"labels that don't fit (add a short_label): {problems}"


def test_every_reply_fits_messenger(bot):
    problems = []
    for name, reply in _replies_for_every_path(bot):
        messages = render.messenger(reply)
        for m in messages:
            assert len(m["text"]) <= render.MS_TEXT_MAX, name
        quick = messages[-1].get("quick_replies", [])
        assert len(quick) <= render.MS_QUICK_REPLIES_MAX, name
        for q in quick:
            if len(q["title"]) > render.MS_TITLE_MAX or q["title"].endswith("…") and q["title"] != "More…":
                problems.append((name, q["title"]))
        if any(b["payload"] == HUMAN for b in reply["buttons"]):
            assert HUMAN in {q["payload"] for q in quick}, f"{name}: Messenger dropped the human option"
    assert not problems, problems


def test_web_is_unchanged():
    reply = {"text": "x", "buttons": [{"label": "A", "payload": "a"}]}
    assert render.web(reply) == [reply]


# --- shapes -------------------------------------------------------------------


def _buttons(n, human_last=True):
    bs = [{"label": f"Option {i}", "payload": f"p{i}"} for i in range(n)]
    if human_last:
        bs[-1] = {"label": "Talk to a person", "payload": HUMAN}
    return bs


def test_three_buttons_are_reply_buttons():
    (m,) = render.whatsapp({"text": "Hi", "buttons": _buttons(3)})
    assert m["interactive"]["type"] == "button"


def test_four_to_ten_are_a_list_with_full_labels_as_descriptions():
    buttons = _buttons(5) + [{"label": "Transfer between eTumba and Airtel/MTN/Zamtel",
                              "short_label": "Send to mobile money", "payload": "x"}]
    (m,) = render.whatsapp({"text": "Hi", "buttons": buttons})
    assert m["interactive"]["type"] == "list"
    row = m["interactive"]["action"]["sections"][0]["rows"][-1]
    assert row["title"] == "Send to mobile money"
    assert row["description"].startswith("Transfer between eTumba")


def test_more_than_ten_keeps_the_human_and_adds_more():
    (m,) = render.whatsapp({"text": "Hi", "buttons": _buttons(14)})
    rows = m["interactive"]["action"]["sections"][0]["rows"]
    assert len(rows) == 10
    assert rows[-1]["id"] == render.MORE_PAYLOAD
    assert HUMAN in {r["id"] for r in rows}


def test_long_body_goes_first_as_text():
    messages = render.whatsapp({"text": "x" * 1500, "buttons": _buttons(2)})
    assert messages[0]["type"] == "text" and len(messages[0]["text"]["body"]) == 1500
    assert len(messages[1]["interactive"]["body"]["text"]) <= render.WA_BODY_MAX


def test_messenger_caps_quick_replies_and_splits_long_text():
    messages = render.messenger({"text": ("word " * 600).strip(), "buttons": _buttons(20)})
    assert len(messages) == 2 and all(len(m["text"]) <= 2000 for m in messages)
    quick = messages[-1]["quick_replies"]
    assert len(quick) == 13 and quick[-1]["payload"] == render.MORE_PAYLOAD
    assert HUMAN in {q["payload"] for q in quick}


# --- self-describing ids ---------------------------------------------------------


def test_stale_city_button_still_finds_the_branch(bot):
    b = bot()
    b.tap("loc_city:Kitwe")  # tapped long after the locator ended
    assert "chisokone" in b.text.lower()
    assert b.session.active_flow is None


def test_time_button_payload_is_stored_as_its_value(bot):
    b = bot()
    b.tap("human_handoff")
    b.say("Mary")
    b.say("0977123456")
    b.say("a loan")
    b.tap("time:Afternoon")
    assert b.session.flow_state["data"]["time"] == "Afternoon"


def test_more_options_resends_what_did_not_fit(bot):
    b = bot(channel="whatsapp")
    b.session.last_replies = [{"text": "x", "buttons": _buttons(12)}]
    b.tap(render.MORE_PAYLOAD)
    assert b.buttons[0] == "p9"
