"""HIDE_DRAFT_NOTES: the demo switch that keeps [CONFIRM …]/[VERIFY …] notes
out of customer replies without touching the content."""
import glob
import json

import pytest
import yaml

from app import config
from app.flows.locator import branch_lines
from app.messages import strip_draft_notes
from app.router import _render

SKIP_KEYS = {"phrases", "legal_note", "notes", "note", "status"}


def _texts(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            if key not in SKIP_KEYS:
                yield from _texts(value)
    elif isinstance(node, list):
        for value in node:
            yield from _texts(value)


def _all_customer_texts():
    for path in sorted(glob.glob(str(config.BASE_DIR / "knowledge/intents/*.yaml"))):
        yield from _texts(yaml.safe_load(open(path, encoding="utf-8")))
    yield from _texts(yaml.safe_load(open(config.BASE_DIR / "knowledge/system_messages.yaml", encoding="utf-8")))
    branches = json.load(open(config.BASE_DIR / "knowledge/branches.json", encoding="utf-8"))["branches"]
    yield branch_lines([b for b in branches if "phone" in b])


def test_off_by_default_notes_stay_visible(monkeypatch):
    monkeypatch.delenv("HIDE_DRAFT_NOTES", raising=False)
    assert not config.hide_draft_notes()
    assert "[CONFIRM" in _render("call {emergency_phone}")


def test_on_no_reply_shows_a_note(monkeypatch):
    monkeypatch.setenv("HIDE_DRAFT_NOTES", "true")
    checked = 0
    for raw in _all_customer_texts():
        if "[CONFIRM" not in raw and "[VERIFY" not in raw and "{emergency_phone}" not in raw:
            continue
        checked += 1
        text = _render(raw)
        assert "[CONFIRM" not in text and "[VERIFY" not in text, text
        lines = text.splitlines()
        assert not any(line.strip() in (".", "-", ":") for line in lines), text
        assert not any(line.rstrip().endswith(":") and line.lstrip().startswith("-") for line in lines), text
        assert "Phone: ." not in text and ": ." not in text, text
    assert checked >= 10


def test_on_emergency_number_falls_back_to_the_contact_centre(monkeypatch):
    monkeypatch.setenv("HIDE_DRAFT_NOTES", "true")
    assert _render("call {emergency_phone} now.") == "call 888 now."
    monkeypatch.setitem(config.CONTACTS, "emergency_phone", "0211 000 000")
    assert _render("call {emergency_phone} now.") == "call 0211 000 000 now."


@pytest.mark.parametrize("raw, expected", [
    ("Saturday morning only\n[CONFIRM: which start time].\nNext line.",
     "Saturday morning only.\nNext line."),
    ("Try this.\n[CONFIRM: status page link.]\nStill stuck? Ask us.",
     "Try this.\nStill stuck? Ask us."),
    ("Resets:\n- eTumba PIN: [CONFIRM: reset route,\n  care line]\n- Online: [CONFIRM]\nOtherwise call.",
     "Resets:\nOtherwise call."),
    ("Here's what I found:\n- Ndola — Mall, Ndola. Phone: [CONFIRM: branch phone]. Hours: 08:00-15:00",
     "Here's what I found:\n- Ndola — Mall, Ndola. Hours: 08:00-15:00"),
    ("- Chongwe — Road, Chongwe. Phone: [CONFIRM: phone]. Hours: [CONFIRM]",
     "- Chongwe — Road, Chongwe."),
    ("No notes here: none at all.", "No notes here: none at all."),
])
def test_strip_draft_notes(raw, expected):
    assert strip_draft_notes(raw) == expected


def test_lost_card_reply_end_to_end(client, monkeypatch):
    monkeypatch.setenv("HIDE_DRAFT_NOTES", "true")
    response = client.post("/chat", json={"message": "someone stole my card"})
    text = " ".join(r["text"] for r in response.json()["replies"])
    assert "[CONFIRM" not in text
    assert "888" in text
