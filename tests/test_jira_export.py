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


# --- Concern #6: the retry list ---------------------------------------------------

def _row(ref):
    import sqlite3

    con = sqlite3.connect(audit.DB_FILE)
    row = con.execute("SELECT jira_key, jira_pending, jira_attempts FROM tickets WHERE ref = ?", (ref,)).fetchone()
    con.close()
    return row


def _real_jira(monkeypatch, outcomes):
    """Real mode with a push that fails or succeeds in the given order."""
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: True)
    calls = []

    def push(kind, ref, fields, transcript, **kwargs):
        calls.append((ref, dict(fields)))
        ok = outcomes.pop(0)
        return {"key": f"CC-{len(calls)}", "url": None, "mode": "real"} if ok else None

    monkeypatch.setattr(jira_export, "push_ticket", push)
    return calls


def _later(minutes):
    import datetime as dt

    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)


def test_a_failed_push_is_retried_until_jira_takes_it(monkeypatch, isolated_data):
    calls = _real_jira(monkeypatch, [False, False, True])
    ref = audit.create_ticket("fraud", {"what_happened": "money gone"}, [{"role": "user", "text": "help"}])
    _join_push(ref)
    assert _row(ref) == (None, audit.JIRA_OWED, 1)
    # Not before the first retry is due: the ticket's own push may still be running.
    assert audit.retry_jira() == {"pushed": 0, "failed": 0, "abandoned": 0}
    assert audit.retry_jira(_later(3)) == {"pushed": 0, "failed": 1, "abandoned": 0}
    assert audit.retry_jira(_later(4)) == {"pushed": 0, "failed": 0, "abandoned": 0}  # backing off
    assert audit.retry_jira(_later(20)) == {"pushed": 1, "failed": 0, "abandoned": 0}
    assert _row(ref) == ("CC-3", 0, 2)
    assert [c[0] for c in calls] == [ref] * 3
    assert calls[-1][1] == {"what_happened": "money gone"}  # the stored ticket, not a guess
    assert audit.retry_jira(_later(200)) == {"pushed": 0, "failed": 0, "abandoned": 0}


def test_a_ticket_still_owed_after_a_day_is_given_up_and_logged(monkeypatch, isolated_data):
    _real_jira(monkeypatch, [False])
    ref = audit.create_ticket("complaint", {"details": "x"}, [])
    _join_push(ref)
    assert audit.retry_jira(_later(config.JIRA_RETRY_HOURS * 60 + 5)) == {"pushed": 0, "failed": 0, "abandoned": 1}
    assert _row(ref)[1] == audit.JIRA_ABANDONED
    assert f"jira push abandoned: {ref}" in audit.JSONL_FILE.read_text(encoding="utf-8")
    assert audit.jira_backlog()["pending"] == 0


def test_nothing_is_owed_in_mock_mode_or_from_before_the_retry_list(monkeypatch, isolated_data):
    monkeypatch.setattr(config, "jira_enabled", lambda: True)
    monkeypatch.setattr(config, "jira_configured", lambda: False)
    mock_ref = audit.create_ticket("callback", {"name": "Test"}, [])
    assert _row(mock_ref)[1] == 0
    import sqlite3

    con = sqlite3.connect(audit.DB_FILE)  # a ticket created before real credentials went live
    con.execute("UPDATE tickets SET jira_key = NULL WHERE ref = ?", (mock_ref,))
    con.commit()
    con.close()
    calls = _real_jira(monkeypatch, [True])
    assert audit.retry_jira(_later(60)) == {"pushed": 0, "failed": 0, "abandoned": 0}
    assert calls == []


def test_the_health_check_fails_when_a_ticket_waits_too_long(monkeypatch, isolated_data):
    from app import health

    monkeypatch.setattr(config, "jira_enabled", lambda: False)
    assert health.jira_backlog()["ok"] is True and health.jira_backlog()["active"] is False
    _real_jira(monkeypatch, [False])
    ref = audit.create_ticket("fraud", {"what_happened": "x"}, [])
    _join_push(ref)
    check = health.jira_backlog()
    assert check["ok"] is True and check["pending"] == 1
    monkeypatch.setattr(config, "JIRA_BACKLOG_MAX_MINUTES", -1)
    check = health.jira_backlog()
    assert check["ok"] is False
    assert ref not in str(check)  # counts only
