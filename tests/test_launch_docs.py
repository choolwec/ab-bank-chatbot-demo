"""Launch, legal and operations documents (R2, W10, W1, L1 and the packs).

These are drafts for the PO, Legal and Compliance. The checks keep them
honest as the code moves: each says it is a draft, the go/no-go file has a
table per milestone, the workshop kit names only intents that exist, and the
phrase-capture template never asks for a name.
"""

import csv
import re

import pytest

from app import config
from app.router import matcher

DOCS = config.BASE_DIR / "docs"
LAUNCH_DOCS = [
    "go-no-go.md",
    "pilot-runbook-whatsapp.md",
    "hosting-requirements-it.md",
    "meta-onboarding-guide.md",
    "legal-compliance-pack.md",
    "dpia-draft.md",
    "phrase-workshop-kit.md",
    "decisions-log.md",
]


def _read(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", LAUNCH_DOCS)
def test_every_launch_doc_says_it_is_a_draft(name):
    head = "\n".join(_read(name).splitlines()[:8]).lower()
    assert "draft" in head, f"{name} must say at the top that it is a draft"


def test_go_no_go_has_a_signed_table_per_milestone():
    text = _read("go-no-go.md")
    for milestone in ("M3", "M4", "M5", "M6"):
        assert re.search(rf"^## {milestone} ", text, re.MULTILINE), milestone
    header = "| # | Criterion | Evidence (file / command / link) | Owner | Status | Signed by / date |"
    assert text.count(header) == 4
    assert "git tag -a" in text  # signed in the commit the release tag points to


def test_workshop_kit_names_only_real_intents():
    listed = set(re.findall(r"^\| \d+ \| [^|]+ \| `([a-z0-9_]+)` \|", _read("phrase-workshop-kit.md"), re.MULTILINE))
    assert listed, "the per-intent capture sheet is missing"
    assert listed <= set(matcher.intents), sorted(listed - set(matcher.intents))


def test_phrase_capture_template_collects_no_names():
    with (DOCS / "phrase-capture-template.csv").open(encoding="utf-8", newline="") as fh:
        header = next(csv.reader(fh))
    assert header == ["intent", "phrasing", "language", "contributor_role"]


def test_decisions_log_leaves_room_for_the_build_streams():
    text = _read("decisions-log.md")
    assert "## Decisions added by the build streams" in text
    assert text.rstrip().endswith("|")  # the placeholder row is the last thing
