"""P9: server-side timing for the load and soak test."""

import json
import time
from pathlib import Path

import pytest

from app import timing
from app.timing import Timings, group_of, percentile
from conftest import chat

WA = Path(__file__).parent / "data" / "wa"


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("ADMIN_USER", "cc-lead")
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse")
    return ("cc-lead", "correct horse")


def test_requests_are_grouped_without_keeping_the_path():
    assert group_of("/chat") == "/chat"
    assert group_of("/webhooks/whatsapp") == "/webhooks/whatsapp"
    assert group_of("/admin/cases/FRD-1/case-update") == "/admin"
    assert group_of("/widget/widget.js") == "/widget"
    assert group_of("/anything/else?x=1") == "other"


def test_percentiles_are_nearest_rank():
    values = [float(v) for v in range(1, 101)]
    assert (percentile(values, 50), percentile(values, 95), percentile(values, 99)) == (50.0, 95.0, 99.0)
    assert percentile([], 95) == 0.0
    assert percentile([7.0], 95) == 7.0


def test_the_window_is_bounded_but_the_count_is_not():
    t = Timings(window=10)
    for ms in range(25):
        t.record("/chat", float(ms))
    s = t.summary()["/chat"]
    assert (s["count"], s["window"], s["max_ms"]) == (25, 10, 24.0)
    assert s["p50_ms"] == 19.0  # of the last ten: 15..24
    t.reset()
    assert t.summary() == {}


def test_admin_timing_reports_chat_latency_queue_and_memory(client, creds):
    assert client.post("/admin/timing/reset", auth=creds).json() == {"reset": True}
    for _ in range(3):
        chat(client, message="what is etumba")
    body = client.get("/admin/timing", auth=creds).json()
    assert body["timings"]["/chat"]["count"] == 3
    assert body["timings"]["/chat"]["p95_ms"] > 0
    assert set(body["inbox"]) == {"oldest_pending_age_s", "counts"}
    assert body["process"]["session_locks"] >= 1
    assert "rss_mb" in body["process"]
    assert "etumba" not in json.dumps(body)  # durations only


def test_admin_timing_is_staff_only(client, monkeypatch):
    monkeypatch.delenv("ADMIN_USER", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert client.get("/admin/timing").status_code == 404
    assert client.post("/admin/timing/reset").status_code == 404


def test_the_worker_times_each_webhook_message(meta_env):
    timing.timings.reset()
    body = json.loads((WA / "text.json").read_text(encoding="utf-8").replace("\"TS\"", f"\"{int(time.time())}\""))
    assert meta_env.post("whatsapp", body).status_code == 200
    meta_env.process()  # waits for the background worker if it got there first
    summary = timing.timings.summary()
    assert summary["worker:whatsapp"]["count"] == 1
    assert summary["/webhooks/whatsapp"]["count"] == 1


def test_rss_is_reported_on_linux():
    value = timing.rss_mb()
    assert value is None or value > 10
