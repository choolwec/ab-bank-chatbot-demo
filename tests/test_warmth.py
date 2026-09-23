"""C11: warmth that never touches the facts."""

from app.messages import MESSAGES


def _callback(b, name="Mary Banda"):
    b.tap("human_handoff")
    b.say(name)
    b.say("0977123456")
    b.say("a loan")
    b.tap("Morning")
    b.tap("confirm_yes")


def test_acknowledgements_rotate_deterministically(bot):
    runs = []
    for _ in range(2):
        b = bot()
        b.tap("human_handoff")
        b.say("Mary Banda")
        b.say("0977123456")
        seen = [b.text.split("\n")[0]]
        b.say("a loan")
        seen.append(b.text.split("\n")[0])
        runs.append(seen)
    assert runs[0] == runs[1]  # same conversation -> same wording
    assert runs[0][1] in MESSAGES["ack"]["variants"]  # the wrapper, then the prompt


def test_acks_vary_across_a_conversation(bot):
    b = bot()
    b.say("i think i was scammed")
    starts = set()
    for answer in ["they called me pretending to be the bank", "yesterday"]:
        b.say(answer)
        starts.add(b.text.split("\n")[0])
    assert len(starts) == 2, starts


def test_name_is_used_exactly_once_per_conversation(bot):
    b = bot()
    _callback(b)
    _callback(b)
    said = " ".join(t["text"] for t in b.session.transcript if t["role"] == "bot")
    assert said.count("Thanks, Mary.") == 1


def test_name_that_is_not_a_name_is_not_repeated(bot):
    b = bot()
    b.tap("human_handoff")
    b.say("0977123456 call me")
    assert "Thanks, 0977" not in b.text


def test_did_you_mean_names_the_category(bot):
    b = bot()
    b.say("loan")
    assert b.action == "did_you_mean"
    assert "I can see this is about loans" in b.text


def test_mixed_suggestions_keep_the_generic_wording(bot):
    b = bot()
    b.say("interest rate")
    if b.action == "did_you_mean":
        assert "I can see this is about" not in b.text


def test_every_button_label_fits_whatsapp():
    long = {k: v["text"] for k, v in MESSAGES.items() if k.startswith("button.") and len(v["text"]) > 20}
    assert not long, long
