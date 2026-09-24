"""N3: the local embedding model in the matcher, tested in hybrid mode.

Skipped when the model hasn't been fetched (`python -m admin.fetch_model`);
CI fetches it, so there it always runs. The character-mode suite
(test_matcher.py) is unchanged and still gates production, where
EMBEDDINGS_ENABLED is off until shadow mode (N4) signs it off.
"""

import shutil
import statistics
import time
from pathlib import Path

import pytest
import yaml

from app import config, embedder
from app.matcher import Matcher

pytestmark = pytest.mark.skipif(not embedder.available(), reason="embedding model not fetched")

GATES_FILE = Path(__file__).parent / "eval" / "gates_embeddings.yaml"

# Where hybrid mode behaves differently from the character matcher on the
# existing suites. STRICT both ways: a new difference fails the build, and a
# listed one that stops happening must be removed from here.
KNOWN_HYBRID_DIFFERENCES = {
    # Negation: embeddings read "I don't want a loan, I want to open an
    # account" as about loans AND accounts -> "did you mean" instead of the
    # account answer. A real weakness; one reason production stays on the
    # character matcher until the N4 shadow review.
    "probe-12-negation",
    # "loan" alone is answered directly (MSME loans) instead of "did you mean".
    "n6-out-of-scope-answer",
    # Answered with savings_account (which states its fees) rather than
    # offering fees_charges in the top 3.
    "how much do you charge for a savings account",
}


@pytest.fixture(scope="module")
def hybrid():
    m = Matcher(use_embeddings=True)
    assert m.mode == "hybrid"
    return m


def test_every_phrase_reaches_its_intent(hybrid):
    failures = []
    for name, intent in hybrid.intents.items():
        for phrase in intent["phrases"]:
            ranked = hybrid.match(phrase)[:3]
            if not any(n == name and s >= config.MEDIUM_CONFIDENCE for n, s in ranked):
                failures.append((name, phrase, ranked))
    assert not failures, failures


def test_canonical_phrase_is_top1(hybrid):
    for name, intent in hybrid.intents.items():
        ranked = hybrid.match(intent["phrases"][0])
        assert ranked[0][0] == name, (name, ranked[:3])


def test_misspellings_and_zambian_english(hybrid):
    from test_matcher import test_misspellings_and_zambian_english as case

    failing = set()
    for mark in case.pytestmark:
        if mark.name == "parametrize":
            for query, expected in mark.args[1]:
                if not any(n == expected for n, _ in hybrid.match(query)[:3]):
                    failing.add(query)
    known = {k for k in KNOWN_HYBRID_DIFFERENCES if " " in k}
    assert failing == known, f"new: {failing - known}; fixed (remove from the list): {known - failing}"


def test_gibberish_scores_low(hybrid):
    ranked = hybrid.match("flurb zzqx vortblatt")
    assert not ranked or ranked[0][1] < config.MEDIUM_CONFIDENCE


def test_eval_gates_in_hybrid_mode(hybrid):
    from admin.eval_report import check_gates, evaluate, format_report

    gates = yaml.safe_load(GATES_FILE.read_text(encoding="utf-8"))["gates"]
    result = evaluate(hybrid)
    failures = check_gates(result.metrics, gates)
    assert not failures, "\n".join(failures) + "\n\n" + format_report(result, gates, show_all=True)


def test_hybrid_beats_character_matching_where_it_matters(hybrid):
    """The reason N3 exists: more right answers, not more wrong ones."""
    from admin.eval_report import evaluate

    char = evaluate(Matcher(use_embeddings=False)).metrics
    hyb = evaluate(hybrid).metrics
    assert hyb["right_direct"] > char["right_direct"]
    assert hyb["wrong_direct"] <= char["wrong_direct"]
    assert hyb["oos_large_direct"] < char["oos_large_direct"]
    assert hyb["one_tap"] >= char["one_tap"]


def test_startup_and_latency_are_within_budget(hybrid, capsys):
    t0 = time.perf_counter()
    Matcher(use_embeddings=True)  # phrase vectors come from the cache
    startup = time.perf_counter() - t0
    samples = []
    for q in ["how much does it cost", "i lost my card yesterday", "where is the passport office"] * 20:
        t = time.perf_counter()
        hybrid.match(q)
        samples.append((time.perf_counter() - t) * 1000)
    p95 = statistics.quantiles(samples, n=20)[-1]
    with capsys.disabled():
        print(f"\n[N3] matcher start-up {startup:.2f}s, match p95 {p95:.1f} ms")
    # Spec: < 3 s and < 20 ms on the target VM; generous here for shared CI runners.
    assert startup < 10 and p95 < 60


def test_a_tampered_model_is_refused(tmp_path):
    for rel in config.EMBED_MODEL_SHA256:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(config.EMBED_MODEL_DIR / rel, dest)
    assert embedder.verify(tmp_path)
    with open(tmp_path / "tokenizer.json", "ab") as fh:
        fh.write(b" ")
    assert not embedder.verify(tmp_path)
    assert embedder.load(tmp_path) is None


def test_kill_switch_and_missing_model_fall_back_to_characters(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "0")
    assert Matcher().mode == "char"
    assert Matcher(use_embeddings=True, embedder=None).mode == "hybrid"
    monkeypatch.setattr(embedder, "load", lambda model_dir=None: None)
    assert Matcher(use_embeddings=True).mode == "char"


def test_every_conversation_script_passes_in_hybrid_mode(hybrid, bot, monkeypatch):
    """The whole router, end to end, with the hybrid matcher swapped in."""
    from app import router
    from test_conversations import CONV_DIR, test_conversation

    monkeypatch.setattr(router, "matcher", hybrid)
    failures = {}
    for path in sorted(CONV_DIR.glob("*.yaml")):
        script = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            test_conversation(bot, script)
        except BaseException as exc:  # pytest.fail raises a BaseException subclass
            failures[script["id"]] = str(exc).splitlines()[0]
    script_ids = {yaml.safe_load(p.read_text(encoding="utf-8"))["id"] for p in CONV_DIR.glob("*.yaml")}
    known = KNOWN_HYBRID_DIFFERENCES & script_ids
    new = {k: v for k, v in failures.items() if k not in known}
    fixed = known - set(failures)
    assert not new and not fixed, f"new: {new}; fixed (remove from the list): {fixed}"



# --- N4: shadow mode ------------------------------------------------------------


def test_shadow_mode_logs_both_decisions_and_never_changes_the_reply(bot, monkeypatch, hybrid):
    import json

    from app import audit, shadow
    from admin.shadow_report import build, disagreements

    monkeypatch.setattr(shadow, "_matcher", hybrid)
    monkeypatch.setattr(shadow, "_tried", True)
    live = bot()
    live.say("what is this etumba thing")
    live_reply = live.text
    monkeypatch.setenv("SHADOW_MATCHER", "1")
    b = bot()
    b.say("what is this etumba thing")
    assert b.text == live_reply  # the customer sees exactly the live answer
    b.say("tell me about tamanga")
    rows = [json.loads(l) for l in audit.JSONL_FILE.read_text(encoding="utf-8").splitlines()]
    shadows = [json.loads(r["text"]) for r in rows if r["action"] == "shadow"]
    assert len(shadows) == 2 and all({"live", "shadow", "agree"} <= set(s) for s in shadows)
    items, total = disagreements(days=1)
    assert total == 2 and items and items[0]["text"]
    assert "disagreements" in build(days=1)


def test_shadow_mode_without_a_model_is_silent(bot, monkeypatch):
    from app import audit, shadow

    monkeypatch.setenv("SHADOW_MATCHER", "1")
    monkeypatch.setattr(shadow, "_matcher", None)
    monkeypatch.setattr(shadow, "_tried", True)
    b = bot()
    b.say("what is etumba")
    assert "shadow" not in audit.JSONL_FILE.read_text(encoding="utf-8")
    assert b.action == "answer"
