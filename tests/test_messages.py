"""C1: every built-in text lives in knowledge/system_messages.yaml."""

import ast
from pathlib import Path

import pytest

from admin import legal_export
from app import messages
from app.flows import FLOWS
from app.messages import MESSAGES, msg

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def test_every_referenced_key_exists():
    missing = messages.referenced_keys() - set(MESSAGES)
    assert not missing, missing


def test_every_flow_convention_key_exists():
    missing = [k for f in FLOWS.values() for k in f.message_keys() if k not in MESSAGES]
    assert not missing, missing


def test_every_message_has_text_and_a_known_status():
    for key, entry in MESSAGES.items():
        assert str(entry.get("text", "")).strip(), key
        assert entry.get("status", "draft") in messages.STATUSES, key


def test_missing_key_raises():
    with pytest.raises(KeyError):
        msg("no.such.message")


def test_fill_keeps_contact_placeholders_for_render():
    text = msg("fraud.finish", ref="FRD-1")
    assert "FRD-1" in text and "{emergency_phone}" in text


def test_legal_export_contains_every_system_message():
    doc = legal_export.build_doc()
    missing = [k for k in MESSAGES if f"`{k}`" not in doc]
    assert not missing, missing
    assert "system:complaint.finish" in doc  # its [CONFIRM] is listed


def _literal_text_values(tree):
    """String constants used as the value of a "text" or "label" key in a
    dict literal (C1 for texts, C11 for button labels)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant) and key.value in ("text", "label")
                    and isinstance(value, (ast.Constant, ast.JoinedStr))
                ):
                    yield node.lineno


def test_no_customer_facing_english_left_in_app():
    """Acceptance (C1, C11): reply texts and button labels are built from
    msg()/button(), never a Python literal."""
    offenders = []
    for path in APP_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [f"{path.name}:{line}" for line in _literal_text_values(tree)]
    assert not offenders, offenders
