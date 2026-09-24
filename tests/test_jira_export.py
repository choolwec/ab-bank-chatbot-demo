"""Jira handoff (§ contact-center integration): off by default, mock mode
when enabled without credentials, never blocks ticket creation on failure."""

from app import audit, config, jira_export


def test_disabled_by_default_returns_none(monkeypatch):
    monkeypatch.setattr(config, "jira_enabled", lambda: False)
    result = jira_export.push_ticket("callback", "CBK-TEST", {"name": "Test"}, [])
    assert result is None


def test_mock_mode_when_enabled_without_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    fields = {"name": "Choolwe", "phone": "0977123456", "topic": "Business account"}
    transcript = [{"role": "user", "text": "hi"}, {"role": "bot", "text": "hello"}]

    result = jira_export.push_ticket("callback", "CBK-20260720-AAAA", fields, transcript)

    assert result["mode"] == "mock"
    assert result["key"].startswith(config.JIRA_MOCK_PROJECT_KEY)
    issues = jira_export.read_mock_issues()
    assert len(issues) == 1
    assert issues[0]["ref"] == "CBK-20260720-AAAA"
    assert "Choolwe" in issues[0]["description"]
    assert "hi" in issues[0]["description"]


def test_mock_keys_increment(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    r1 = jira_export.push_ticket("fraud", "FRD-1", {"what_happened": "x"}, [])
    r2 = jira_export.push_ticket("fraud", "FRD-2", {"what_happened": "y"}, [])
    assert r1["key"] != r2["key"]


def test_fraud_gets_highest_priority(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    jira_export.push_ticket("fraud", "FRD-3", {"what_happened": "stolen"}, [])
    issues = jira_export.read_mock_issues()
    assert issues[0]["priority"] == "Highest"


def test_create_ticket_never_raises_when_jira_push_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        jira_export, "push_ticket", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    ref = audit.create_ticket("callback", {"name": "Test"}, [])
    assert ref.startswith("CBK-")


def test_preview_renders_without_crashing_when_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "jira_enabled", lambda: False)
    html = jira_export.render_jira_preview()
    assert "Jira" in html
    assert "No tickets yet" in html


def _join_push(ref):
    import threading

    for thread in threading.enumerate():
        if thread.name == f"jira-push-{ref}":
            thread.join(5)


def test_a_real_jira_push_never_holds_up_the_reply(monkeypatch, isolated_data):
    """P9: with real credentials the push runs beside the reply, not in it."""
    import threading
    import time

    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: True)
    release, pushed = threading.Event(), []

    def slow_push(kind, ref, *args, **kwargs):
        release.wait(5)
        pushed.append(ref)
        return {"key": "CC-9", "url": None, "mode": "real"}

    monkeypatch.setattr(jira_export, "push_ticket", slow_push)
    start = time.perf_counter()
    ref = audit.create_ticket("callback", {"name": "Test"}, [])
    assert time.perf_counter() - start < 1 and pushed == []
    release.set()
    _join_push(ref)
    assert pushed == [ref]


def test_the_background_push_sends_the_transcript_as_stored(monkeypatch, isolated_data):
    """The session keeps growing after the ticket is created (the finish reply
    is appended next); the Jira issue must carry the ticket's own snapshot."""
    import threading

    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: True)
    release, seen = threading.Event(), []

    def slow_push(kind, ref, fields, transcript, **kwargs):
        release.wait(5)
        seen.append((dict(fields), list(transcript)))
        return None

    monkeypatch.setattr(jira_export, "push_ticket", slow_push)
    transcript = [{"role": "user", "text": "someone took money"}]
    fields = {"what_happened": "someone took money"}
    ref = audit.create_ticket("fraud", fields, transcript)
    transcript.append({"role": "bot", "text": "later message"})
    fields["extra"] = "later"
    release.set()
    _join_push(ref)
    assert seen == [({"what_happened": "someone took money"}, [{"role": "user", "text": "someone took money"}])]


def test_a_failing_background_push_is_still_harmless(monkeypatch, isolated_data):
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: True)
    monkeypatch.setattr(
        jira_export, "push_ticket", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    ref = audit.create_ticket("fraud", {"what_happened": "x"}, [])
    _join_push(ref)
    assert ref.startswith("FRD-")


def test_mock_mode_still_writes_before_the_reply(monkeypatch, isolated_data):
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: False)
    ref = audit.create_ticket("callback", {"name": "Test"}, [])
    assert jira_export.read_mock_issues()[0]["ref"] == ref
