"""Red-team input suite: hostile input must never crash, leak, or dead-end."""

from pathlib import Path

from conftest import chat

INPUTS_FILE = Path(__file__).parent / "redteam_inputs.txt"


def _inputs():
    lines = INPUTS_FILE.read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]


def test_redteam_inputs(client):
    assert _inputs(), "red-team input file is empty"
    for line in _inputs():
        sid = chat(client)["session_id"]
        data = chat(client, sid, message=line[:900])
        text = " ".join(r["text"] for r in data["replies"])
        assert data["replies"], line
        assert data["replies"][-1]["buttons"], f"dead end for: {line}"
        # never echo card digits back
        assert "4111 1111 1111 1111" not in text
