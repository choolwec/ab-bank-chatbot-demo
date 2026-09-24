"""E2: multi-turn conversation scripts in tests/conversations/*.yaml.

Each file is one conversation driven through router.handle() in-process, with
a fresh session and a temporary data directory (never touches data/).

    id: probe-06-typed-cancel
    channel: whatsapp  # optional; default web (P5 merges bubbles on Meta channels)
    fixes: C2          # the ticket that makes this pass
    xfail: true        # strict: an unexpected pass fails the build
    turns:
      - payload: human_handoff
      - say: cancel
        expect: {action: cancel, active_flow: null}

expect keys (all optional, all checked after that turn):
  action / action_in       meta["action"] equals / is one of
  intent / intent_in       meta["intent"] equals / is one of
  active_flow              session.active_flow (null = no flow)
  flow_step                the active flow's current step field name
  flow_data_has            {field: substring} -- field present and contains it
  flow_data_lacks          {field: substring} -- field absent or lacks it
  strikes                  session.strikes
  text_contains / text_lacks   case-insensitive substrings of all reply text
  last_buttons_include     payloads on the last reply's buttons
  ticket_created           a ticket of this type was created on this turn
  replies_max              at most this many bubbles on this turn
  bot_messages_max         at most this many bot bubbles in the whole script
                           so far (M1: <= 4 per scripted fraud report)
"""

import sqlite3
from pathlib import Path

import pytest
import yaml

from app import audit

CONV_DIR = Path(__file__).parent / "conversations"


def _scripts():
    params = []
    for path in sorted(CONV_DIR.glob("*.yaml")):
        script = yaml.safe_load(path.read_text(encoding="utf-8"))
        marks = []
        if script.get("xfail"):
            marks.append(
                pytest.mark.xfail(strict=True, reason=f"fixed by {script.get('fixes')}")
            )
        params.append(pytest.param(script, id=script["id"], marks=marks))
    return params


def _ticket_count(kind):
    if not audit.DB_FILE.exists():
        return 0
    con = sqlite3.connect(audit.DB_FILE)
    try:
        return con.execute("SELECT COUNT(*) FROM tickets WHERE type = ?", (kind,)).fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        con.close()


def _current_step(session):
    from app.flows import FLOWS

    flow = FLOWS.get(session.active_flow)
    steps = getattr(flow, "steps", None)
    if not steps:
        return None
    i = session.flow_state.get("step", 0)
    return steps[i] if i < len(steps) else None


def check_turn(b, exp, before_tickets, bot_messages, where):
    replies, meta = b.last
    text = b.text.lower()
    data = b.session.flow_state.get("data", {}) if b.session.active_flow else {}

    def fail(msg):
        pytest.fail(f"{where}: {msg}\n  meta={meta}\n  text={b.text[:400]!r}")

    if "action" in exp and meta.get("action") != exp["action"]:
        fail(f"action {meta.get('action')!r} != {exp['action']!r}")
    if "action_in" in exp and meta.get("action") not in exp["action_in"]:
        fail(f"action {meta.get('action')!r} not in {exp['action_in']}")
    if "intent" in exp and meta.get("intent") != exp["intent"]:
        fail(f"intent {meta.get('intent')!r} != {exp['intent']!r}")
    if "intent_in" in exp and meta.get("intent") not in exp["intent_in"]:
        fail(f"intent {meta.get('intent')!r} not in {exp['intent_in']}")
    if "active_flow" in exp and b.session.active_flow != exp["active_flow"]:
        fail(f"active_flow {b.session.active_flow!r} != {exp['active_flow']!r}")
    if "flow_step" in exp and _current_step(b.session) != exp["flow_step"]:
        fail(f"flow step {_current_step(b.session)!r} != {exp['flow_step']!r}")
    for field, needle in (exp.get("flow_data_has") or {}).items():
        if needle.lower() not in str(data.get(field, "")).lower():
            fail(f"flow data {field}={data.get(field)!r} lacks {needle!r}")
    for field, needle in (exp.get("flow_data_lacks") or {}).items():
        if field in data and needle.lower() in str(data[field]).lower():
            fail(f"flow data {field}={data[field]!r} should not contain {needle!r}")
    if "strikes" in exp and b.session.strikes != exp["strikes"]:
        fail(f"strikes {b.session.strikes} != {exp['strikes']}")
    for needle in exp.get("text_contains", []):
        if str(needle).lower() not in text:
            fail(f"reply lacks {needle!r}")
    for needle in exp.get("text_lacks", []):
        if str(needle).lower() in text:
            fail(f"reply contains {needle!r}")
    for payload in exp.get("last_buttons_include", []):
        if payload not in b.buttons:
            fail(f"last buttons {b.buttons} lack {payload!r}")
    if "ticket_created" in exp:
        kind = exp["ticket_created"]
        if _ticket_count(kind) <= before_tickets.get(kind, 0):
            fail(f"no {kind} ticket created")
    if "replies_max" in exp and len(replies) > exp["replies_max"]:
        fail(f"{len(replies)} bubbles > {exp['replies_max']}")
    if "bot_messages_max" in exp and bot_messages > exp["bot_messages_max"]:
        fail(f"{bot_messages} bot messages so far > {exp['bot_messages_max']}")


@pytest.mark.parametrize("script", _scripts())
def test_conversation(bot, script):
    b = bot(channel=script.get("channel", "web"))
    bot_messages = 0
    for n, turn in enumerate(script["turns"], 1):
        before = {k: _ticket_count(k) for k in ("fraud", "complaint", "callback")}
        if "say" in turn:
            b.say(str(turn["say"]))
        else:
            b.tap(turn["payload"])
        bot_messages += len(b.last[0])
        assert b.last[0][-1]["buttons"], f"turn {n}: dead end"
        if turn.get("expect"):
            label = turn.get("say", turn.get("payload"))
            check_turn(b, turn["expect"], before, bot_messages, f"turn {n} ({label!r})")


def test_every_script_has_an_id_and_turns():
    ids = set()
    for path in CONV_DIR.glob("*.yaml"):
        script = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert script.get("id") and script.get("turns"), path.name
        assert script["id"] not in ids, script["id"]
        ids.add(script["id"])
        if script.get("xfail"):
            assert script.get("fixes"), f"{path.name}: xfail needs a fixes: ticket"
