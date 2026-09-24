"""P9: the load script's traffic stays valid as fixtures and flows change.

research/load/load.py is research code (like the matcher benchmark), but a
load test that quietly sends malformed webhooks or dead-ends its flows would
measure the wrong thing, so its traffic is checked here, in-process.
"""

import hashlib
import hmac
import importlib.util
import json
from pathlib import Path

from app.channels import whatsapp

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("load", ROOT / "research" / "load" / "load.py")
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)


def test_webhook_bodies_parse_with_fresh_ids_and_verify_with_the_secret():
    traffic = load.Traffic(seed=1)
    ids = set()
    for _ in range(200):
        kind, raw = traffic.wa_body()
        messages, statuses = whatsapp.parse(json.loads(raw))
        assert messages or statuses, kind
        for m in messages:
            assert m.msg_id.startswith("wamid.LOAD") and m.msg_id not in ids
            ids.add(m.msg_id)
            assert m.user_key in traffic.wa_users
        sig = "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
        assert whatsapp.signature_ok(raw, sig, "s3cret")


def test_fraud_and_callback_paths_end_in_a_ticket(bot):
    for steps in (load.FRAUD, load.CALLBACK):
        b = bot()
        for step in steps:
            b.tap(step["payload"]) if "payload" in step else b.say(step["message"])
        assert load.TICKET_REF.search(b.text), b.text


def test_faq_questions_come_from_the_held_out_set():
    traffic = load.Traffic(seed=2)
    kind, steps = traffic.conversation()
    questions = {traffic.question() for _ in range(50)}
    assert questions <= set(traffic.in_scope) | set(traffic.out_of_scope)
    assert steps[0] == {"open": True}
