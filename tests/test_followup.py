"""H1 (tickets carry channel + reply address), W7 (templates), W9 (channel
answer variants)."""

import json
import re
import sqlite3
import time

import pytest

from app import admin_cases, audit, config
from test_whatsapp import RAW_NUMBER, say


def _fraud_on_whatsapp(meta_env):
    say(meta_env, "i think i was scammed")
    say(meta_env, "they called pretending to be the bank")
    say(meta_env, "yesterday")
    say(meta_env, "eTumba")
    say(meta_env, "0977123456")
    (ref, reply_to) = sqlite3.connect(audit.DB_FILE).execute("SELECT ref, reply_to FROM tickets").fetchone()
    return ref, json.loads(reply_to)


def test_ticket_carries_channel_sealed_address_and_window(meta_env):
    ref, reply_to = _fraud_on_whatsapp(meta_env)
    assert reply_to["channel"] == "whatsapp" and len(reply_to["user_hash"]) == 32
    assert reply_to["sealed"] and RAW_NUMBER not in reply_to["sealed"]
    assert reply_to["window_open_until"]
    from app.identity import unseal

    assert unseal(reply_to["sealed"]) == RAW_NUMBER


def test_jira_description_says_how_to_reply(meta_env, monkeypatch):
    monkeypatch.setenv("JIRA_ENABLED", "1")
    _fraud_on_whatsapp(meta_env)
    issue = json.loads((meta_env.tmp / "jira_mock.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    text = json.dumps(issue)
    assert "Channel: whatsapp" in text and "case_update" in text
    assert RAW_NUMBER not in text


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "cc-lead")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse")
    return ("cc-lead", "correct horse")


def test_cases_page_offers_the_template_once_the_window_closes(meta_env, admin):
    ref, _ = _fraud_on_whatsapp(meta_env)
    page = meta_env.client.get("/admin/cases", auth=admin).text
    assert ref in page and "Reply in the inbox" in page and "Send case_update" not in page

    con = sqlite3.connect(audit.DB_FILE)
    (reply_to,) = con.execute("SELECT reply_to FROM tickets WHERE ref = ?", (ref,)).fetchone()
    info = json.loads(reply_to)
    info["window_open_until"] = "2020-01-01T00:00:00+00:00"
    con.execute("UPDATE tickets SET reply_to = ? WHERE ref = ?", (json.dumps(info), ref))
    con.commit()
    con.close()

    page = meta_env.client.get("/admin/cases", auth=admin).text
    token = re.search(r"name='csrf' value='([0-9a-f]+)'", page).group(1)
    r = meta_env.client.post(f"/admin/cases/{ref}/case-update", auth=admin, content=f"csrf={token}".encode(),
                             headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200
    sent = [m for m in meta_env.outbox("whatsapp") if m.get("type") == "template"]
    assert sent[-1]["template"]["name"] == "case_update"
    assert sent[-1]["template"]["components"][0]["parameters"][0]["text"] == ref
    assert sent[-1]["to"].startswith("hash:")  # the mock outbox never holds the number


def test_templates_are_neutral_and_link_free():
    templates = admin_cases.load_templates()
    assert set(templates) == {"case_received", "case_update", "callback_scheduled"}
    for name, t in templates.items():
        assert "{{1}}" in t["body"], name  # always quotes the reference
        assert "http" not in t["body"] and "www." not in t["body"], name
        assert t["category"] == "UTILITY"


def test_contact_details_on_whatsapp_does_not_say_whatsapp_us(bot):
    web = bot()
    web.tap("contact_details")
    assert "WhatsApp:" in web.text
    wa = bot(channel="whatsapp")
    wa.tap("contact_details")
    assert "WhatsApp:" not in wa.text and "already chatting" in wa.text
