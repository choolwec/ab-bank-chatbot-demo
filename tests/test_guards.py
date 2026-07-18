"""PII masking and urgent-scan unit tests (§3.3, acceptance §3.5)."""

from app import guards


def test_card_number_masked():
    masked, findings = guards.mask("my card is 5454 1212 3434 5656 please help")
    assert "5454" not in masked
    assert "[CARD REDACTED]" in masked
    assert "card_number" in findings


def test_card_number_with_dashes_masked():
    masked, _ = guards.mask("4111-1111-1111-1111")
    assert "4111" not in masked


def test_nrc_masked():
    masked, findings = guards.mask("my nrc is 123456/78/9")
    assert "123456/78/9" not in masked
    assert "nrc" in findings


def test_pin_value_masked_but_sentence_kept():
    masked, findings = guards.mask("my pin is 1234")
    assert "1234" not in masked
    assert "pin" in masked.lower()
    assert "credential" in findings


def test_password_assignment_masked():
    masked, findings = guards.mask("password: hunter2")
    assert "hunter2" not in masked
    assert "credential" in findings


def test_forgot_pin_not_mangled():
    # A question ABOUT a PIN must survive so the intent can match.
    masked, findings = guards.mask("i forgot my pin")
    assert masked == "i forgot my pin"
    assert findings == []


def test_zambian_phone_number_passes_through():
    # The callback flow needs phone numbers; 10-12 digits are not card-shaped.
    masked, findings = guards.mask("call me on 0977123456")
    assert "0977123456" in masked
    assert findings == []


def test_account_number_in_context_masked():
    masked, findings = guards.mask("my account number is 62001234567")
    assert "62001234567" not in masked
    assert "account_number" in findings


def test_clean_caps_length_and_strips_zero_width():
    long = "a" * 5000
    assert len(guards.clean(long)) <= 500
    assert guards.clean("he​llo") != "he​llo"


def test_urgent_scan_fraud():
    assert guards.urgent_scan("i think someone hacked my account") == ("fraud", "fraud")
    assert guards.urgent_scan("there is money missing from my account") == ("fraud", "fraud")


def test_urgent_scan_lost_card():
    assert guards.urgent_scan("I lost my card yesterday") == ("fraud", "lost_card")


def test_urgent_scan_complaint():
    kind, _sub = guards.urgent_scan("I want to complain about poor service")
    assert kind == "complaint"


def test_urgent_scan_clean_message():
    assert guards.urgent_scan("what is etumba") is None
