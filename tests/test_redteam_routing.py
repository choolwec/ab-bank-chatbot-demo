"""S3: red-team routing. Where a hostile or tricky message ENDS UP, not just
that it doesn't crash. Cases live in tests/data/redteam.yaml."""

from pathlib import Path

import pytest
import yaml

from app import audit

CASES = yaml.safe_load(
    (Path(__file__).parent / "data" / "redteam.yaml").read_text(encoding="utf-8")
)["cases"]


def _id(case):
    return case["text"][:50]


def test_suite_covers_the_original_inputs():
    original = [
        l.strip()
        for l in (Path(__file__).parent / "redteam_inputs.txt").read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    texts = {c["text"].strip() for c in CASES}
    missing = [l for l in original if l not in texts]
    assert not missing, missing


@pytest.mark.parametrize("case", CASES, ids=_id)
def test_redteam_routing(bot, case):
    b = bot()
    replies, meta = b.say(case["text"])
    exp = case["expect"]
    reply_text = b.text.lower()

    assert replies and replies[-1]["buttons"], "dead end"
    if "action" in exp:
        assert meta.get("action") == exp["action"], meta
    if "action_in" in exp:
        assert meta.get("action") in exp["action_in"], meta
    if "intent" in exp:
        assert meta.get("intent") == exp["intent"], meta
    if "flow" in exp:
        assert b.session.active_flow == exp["flow"]
    for flow in exp.get("not_flow", []):
        assert b.session.active_flow != flow, (flow, meta)
    for needle in exp.get("text_lacks", []):
        assert str(needle).lower() not in reply_text, needle

    logged = audit.JSONL_FILE.read_text(encoding="utf-8")
    for needle in exp.get("audit_has", []):
        assert needle in logged, needle
    for needle in exp.get("audit_lacks", []):
        assert needle not in logged, needle
