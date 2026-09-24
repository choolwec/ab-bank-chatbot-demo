"""E3: held-out evaluation gates. Content edits are deploys; this is the test
that catches a phrase edit making the bot confidently answer questions it
doesn't cover. Numbers: python -m admin.eval_report"""

from admin.eval_report import check_gates, evaluate, format_report, load_gates, load_heldout
from app.router import matcher


def test_eval_gates_hold():
    result = evaluate(matcher)
    gates = load_gates()
    failures = check_gates(result.metrics, gates)
    assert not failures, "\n".join(failures) + "\n\n" + format_report(result, gates, show_all=True)


# 11 in-scope phrasings already appeared verbatim in intent phrases when the
# set was moved here (E3, 2026-09-23), so the baseline includes them. They
# are grandfathered, rather than removed, to keep the gates pinned to the
# recorded baseline -- N1 replaces this seed set. No NEW overlap is allowed.
GRANDFATHERED_OVERLAP = {
    "my account is dormant", "what is your swift code", "etumba charges",
    "move money from my bank account to etumba", "what is yaka",
    "loan for my business", "who can be my guarantor",
    "can i use my car as collateral", "how do i apply for a loan",
    "are you a robot", "i forgot my pin",
}


def test_heldout_never_copied_into_intent_phrases():
    """A held-out phrasing pasted into phrases: stops being a test."""
    phrases = {
        str(p).lower().strip()
        for intent in matcher.intents.values()
        for p in intent.get("phrases", [])
    }
    heldout = load_heldout()
    from admin.eval_report import load_oos

    from admin.eval_report import load_banking77

    b77 = load_banking77()
    leaked = [c["text"] for c in heldout["in_scope"] + heldout["out_of_scope"] + load_oos()
              + b77["in_scope"] + b77["out_of_scope"]
              if c["text"].lower().strip() in phrases
              and c["text"].lower().strip() not in GRANDFATHERED_OVERLAP]
    assert not leaked, leaked


def test_heldout_intents_exist():
    missing = {c["intent"] for c in load_heldout()["in_scope"]} - set(matcher.intents)
    assert not missing, missing


class _LookalikeAnswered:
    """The real matcher, except one hard out-of-scope lookalike now gets a
    confident direct answer -- what a careless phrase edit would do."""

    def match(self, text, top_n=5):
        if text == "how do i open a facebook account":
            return [("account_opening_how", 0.99)]
        if text == "i need a lawyer":
            return [("loan_apply_how", 0.10)]
        return matcher.match(text, top_n)


def test_gates_fail_when_a_lookalike_starts_getting_answered():
    heldout = load_heldout()
    # Compare against gates set exactly at the real matcher's own numbers,
    # so the test doesn't depend on how much headroom the real gates have.
    real = evaluate(matcher, heldout).metrics
    tight = {"oos_direct_max": real["oos_direct"]}
    assert not check_gates(real, tight)
    worse = dict(real)
    worse["oos_direct"] = real["oos_direct"] + 1 / real["n_out_of_scope"]
    assert check_gates(worse, tight)
    # and end to end through evaluate(): one extra confident OOS answer
    other = heldout["out_of_scope"] + [{"text": "how do i open a facebook account"}]
    tampered = evaluate(_LookalikeAnswered(), {**heldout, "out_of_scope": other})
    assert tampered.oos_direct[-1][0] == "how do i open a facebook account"



def test_n2_out_of_scope_set_is_large_and_unique():
    from admin.eval_report import load_oos

    items = load_oos()
    texts = [i["text"].lower().strip() for i in items]
    assert len(items) >= 300 and len(set(texts)) == len(texts)
    assert all(i.get("category") for i in items)



# --- N1 labelling pipeline ------------------------------------------------------


def test_import_labels_keeps_only_agreed_rows():
    from admin.import_labels import import_rows

    rows = [
        {"text": "wer is ur kitwe branch", "label_a": "branch_locator", "label_b": "branch_locator"},
        {"text": "how do i buy shares", "label_a": "oos", "label_b": "oos"},
        {"text": "i want to borrow", "label_a": "loan_apply_how", "label_b": "msme_loan"},
        {"text": "gibberish", "label_a": "no_such_intent", "label_b": "no_such_intent"},
        {"text": "unlabelled", "label_a": "", "label_b": ""},
    ]
    golden, added, disagreements, unknown = import_rows(rows, set(matcher.intents))
    assert added == 2
    assert golden["in_scope"] == [{"text": "wer is ur kitwe branch", "intent": "branch_locator", "source": "labelled"}]
    assert golden["out_of_scope"][0]["text"] == "how do i buy shares"
    assert disagreements == [("i want to borrow", "loan_apply_how", "msme_loan")]
    assert unknown == [("gibberish", "no_such_intent")]


def test_export_drops_anything_that_still_looks_personal():
    from admin.export_utterances import looks_personal

    for text in ["call me on 0977123456", "my email is a@b.com", "account [ACCOUNT REDACTED]",
                 "card 4111111111111111", "my nrc is 123456/78/9"]:
        assert looks_personal(text), text
    for text in ["what is etumba", "how much is tamanga", "where is the kitwe branch"]:
        assert not looks_personal(text), text


def test_export_reads_masked_user_messages(bot):
    from admin.export_utterances import export

    b = bot()
    b.say("what is etumba")
    b.say("what is etumba")          # de-duplicated
    b.say("call me on 0977123456")   # dropped by the second PII check
    rows = export(days=1)
    texts = [r["text"] for r in rows]
    assert texts.count("what is etumba") == 1
    assert not any("0977123456" in t for t in texts)
    assert rows[0]["predicted_intent"] == "etumba_what_is" and rows[0]["action"] == "answer"
