"""Load and soak test (ticket P9). Research code: not part of the app or suite.

Local, against its own uvicorn (one worker, as in production):
    python research/load/load.py --spawn --rate 20 --minutes 5 --out research/load/local.json

Staging or production (the admin pages must be on; the WhatsApp app secret
is the one that server checks, so the signed posts are accepted):
    python research/load/load.py --url https://<host> --admin-user <u> --admin-password <p> \\
        --wa-secret <app secret> --rate 20 --minutes 30

Traffic is open-loop at --rate requests/s, so a slow server never lowers the
offered load:
  70%  /chat turns from real paths: FAQ questions (the held-out evaluation
       phrasings) with a button tap, the four-message fraud report (C8) and
       the callback request (C7). Each conversation's turns go in order.
  30%  signed WhatsApp webhook posts built from tests/data/wa/*.json with
       fresh message ids and timestamps, from 200 synthetic customers.

Recorded: client-side p50/p95/p99 per kind, status codes, whether fraud and
callback conversations ended with a ticket reference, the server's own timing
per route and per worker message (/admin/timing), its RSS every 30 s, and the
inbox queue age every 5 s. Targets: server p95 <= 150 ms and no memory growth.

--spawn only:
  --fake-latency-ms N  point the WhatsApp sender and Jira at a local fake that
                       answers after N ms, instead of mock mode, to see what
                       real network round trips do to the worker and to /chat
  --shadow             SHADOW_MATCHER=true, as on staging
"""

import argparse
import asyncio
import hashlib
import hmac
import http.server
import json
import os
import random
import re
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter, deque
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[2]
WA_DIR = ROOT / "tests" / "data" / "wa"
TICKET_REF = re.compile(r"\b(FRD|CBK|CMP)-\d{8}-[A-Z0-9]{4}\b")
SPAWN_SECRET = "load-test-app-secret"
SPAWN_ADMIN = ("load", "load-test-password")

FRAUD = [{"message": "I lost my card yesterday at cairo branch"}, {"message": "yes"},
         {"message": "0977123456", "expect_ticket": True}]
CALLBACK = [{"payload": "human_handoff"}, {"message": "Mary Banda"}, {"message": "0977123456"},
            {"message": "a loan"}, {"message": "2"}, {"message": "yes please", "expect_ticket": True}]


def phrasings():
    data = yaml.safe_load((ROOT / "tests" / "eval" / "heldout.yaml").read_text(encoding="utf-8"))
    return [i["text"] for i in data["in_scope"]], [i["text"] for i in data["out_of_scope"]]


class Traffic:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.in_scope, self.out_of_scope = phrasings()
        self.templates = {p.stem: p.read_text(encoding="utf-8") for p in WA_DIR.glob("*.json")}
        self.wa_users = [f"2609{self.rng.randrange(10**7, 10**8)}" for _ in range(200)]

    def question(self) -> str:
        pool = self.out_of_scope if self.rng.random() < 0.1 else self.in_scope
        return self.rng.choice(pool)

    def conversation(self) -> tuple[str, list[dict]]:
        roll = self.rng.random()
        if roll < 0.6:
            return "faq", [{"open": True}, {"message": self.question()}, {"tap": True},
                           {"message": self.question()}]
        if roll < 0.8:
            return "fraud", [{"open": True}] + FRAUD
        return "callback", [{"open": True}] + CALLBACK

    def wa_body(self) -> tuple[str, bytes]:
        kind = self.rng.choices(["text", "button_reply", "list_reply", "status", "image", "location"],
                                weights=[60, 10, 10, 10, 5, 5])[0]
        user = self.rng.choice(self.wa_users)
        raw = self.templates[kind].replace('"TS"', f'"{int(time.time())}"')
        body = json.loads(raw)
        value = body["entry"][0]["changes"][0]["value"]
        for contact in value.get("contacts", []):
            contact["wa_id"] = user
        for m in value.get("messages", []):
            m["id"] = f"wamid.LOAD{uuid.uuid4().hex}"
            m["from"] = user
            if kind == "text":
                m["text"]["body"] = self.question()
        for st in value.get("statuses", []):
            st["id"] = f"wamid.LOADOUT{uuid.uuid4().hex}"
            st["recipient_id"] = user
            st["status"] = self.rng.choice(["sent", "delivered", "read"])
            st.pop("errors", None)
        return kind, json.dumps(body).encode()


class Stats:
    def __init__(self):
        self.latency = {"chat": [], "webhook": []}
        self.slow = {"chat": [], "webhook": []}  # (seconds into the run, ms) over 150 ms
        self.status = Counter()
        self.errors = Counter()
        self.sent = Counter()
        self.flows = Counter()
        self.started = time.perf_counter()

    def add(self, kind, ms, status):
        self.latency[kind].append(ms)
        self.status[f"{kind}:{status}"] += 1
        if ms > 150:
            self.slow[kind].append((round(time.perf_counter() - self.started - ms / 1000, 1), round(ms)))


def pct(values, p):
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, int(-(-p * len(ordered) // 100)) - 1)]


# --- the server under test -------------------------------------------------------

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeUpstream(http.server.BaseHTTPRequestHandler):
    """Answers every POST after a delay: Graph API sends and Jira issues."""

    delay = 0.0

    def do_POST(self):  # noqa: N802
        self.rfile.read(int(self.headers.get("content-length") or 0))
        time.sleep(self.delay)
        body = json.dumps({"key": "CC-1", "messages": [{"id": "wamid.FAKE"}]}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def start_fake_upstream(delay_ms: int) -> str:
    FakeUpstream.delay = delay_ms / 1000
    server = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), FakeUpstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


def spawn(args) -> tuple[subprocess.Popen, str, Path]:
    data = Path(tempfile.mkdtemp(prefix="abz-load-"))
    port = free_port()
    env = dict(os.environ, ABZ_DATA_DIR=str(data), WA_APP_SECRET=SPAWN_SECRET, WA_VERIFY_TOKEN="load",
               ADMIN_USER=SPAWN_ADMIN[0], ADMIN_PASSWORD=SPAWN_ADMIN[1],
               RATE_LIMIT_PER_MINUTE="1000000",  # every request comes from 127.0.0.1
               PYTHONDONTWRITEBYTECODE="1")
    for var in ("SESSION_STORE", "JIRA_BASE_URL", "WA_ACCESS_TOKEN", "WA_PHONE_NUMBER_ID", "MS_PAGE_TOKEN"):
        env.pop(var, None)
    if args.shadow:
        env["SHADOW_MATCHER"] = "true"
    if args.fake_latency_ms:
        fake = start_fake_upstream(args.fake_latency_ms)
        env.update(GRAPH_BASE_URL=fake, WA_ACCESS_TOKEN="fake", WA_PHONE_NUMBER_ID="fake",
                   JIRA_BASE_URL=fake, JIRA_EMAIL="load@example.invalid", JIRA_API_TOKEN="fake",
                   JIRA_PROJECT_KEY="CC")
    log = open(data / "uvicorn.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
         "--workers", "1", "--no-access-log"],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                return proc, base, data
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    proc.kill()
    sys.exit(f"the server did not start; see {data / 'uvicorn.log'}")


# --- the load ----------------------------------------------------------------------

async def web_turn(client, conv, stats, ready):
    step = conv["steps"].pop(0)
    body = {"session_id": conv.get("session_id")}
    if "message" in step:
        body["message"] = step["message"]
    elif "payload" in step:
        body["payload"] = step["payload"]
    elif step.get("tap"):
        buttons = conv.get("buttons") or []
        if buttons:
            body["payload"] = conv["rng"].choice(buttons)
        else:
            body["message"] = "menu"
    start = time.perf_counter()
    try:
        r = await client.post("/chat", json=body)
        stats.add("chat", (time.perf_counter() - start) * 1000, r.status_code)
        if r.status_code == 200:
            data = r.json()
            conv["session_id"] = data["session_id"]
            replies = data.get("replies") or []
            conv["buttons"] = [b["payload"] for b in (replies[-1].get("buttons") or [])] if replies else []
            if step.get("expect_ticket"):
                text = " ".join(x.get("text", "") for x in replies)
                stats.flows[f"{conv['kind']}:{'ticket' if TICKET_REF.search(text) else 'NO ticket'}"] += 1
    except httpx.HTTPError as exc:
        stats.errors[f"chat:{type(exc).__name__}"] += 1
    if conv["steps"]:
        ready.append(conv)


async def wa_post(client, traffic, stats, secret):
    kind, raw = traffic.wa_body()
    sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    stats.sent[f"wa:{kind}"] += 1
    start = time.perf_counter()
    try:
        r = await client.post("/webhooks/whatsapp", content=raw,
                              headers={"content-type": "application/json", "x-hub-signature-256": sig})
        stats.add("webhook", (time.perf_counter() - start) * 1000, r.status_code)
    except httpx.HTTPError as exc:
        stats.errors[f"webhook:{type(exc).__name__}"] += 1


async def sampler(client, auth, series, stop):
    start = time.time()
    last_rss = -30.0
    while not stop.is_set():
        try:
            r = await client.get("/admin/timing", auth=auth)
            if r.status_code == 200:
                data = r.json()
                t = round(time.time() - start, 1)
                series["queue"].append((t, data["inbox"]["oldest_pending_age_s"],
                                        data["inbox"]["counts"].get("new", 0)))
                if t - last_rss >= 30:
                    series["rss"].append((t, data["process"]["rss_mb"], data["process"]["session_locks"]))
                    last_rss = t
        except httpx.HTTPError:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass


async def run(args, base, auth, secret):
    traffic = Traffic(args.seed)
    stats = Stats()
    series = {"queue": [], "rss": []}
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    async with httpx.AsyncClient(base_url=base, timeout=30, limits=limits) as client:
        await client.post("/admin/timing/reset", auth=auth)
        stop = asyncio.Event()
        sampling = asyncio.create_task(sampler(client, auth, series, stop))
        ready: deque = deque()
        tasks = set()
        loop = asyncio.get_running_loop()
        interval = 1 / args.rate
        started = loop.time()
        stats.started = time.perf_counter()
        end = started + args.minutes * 60
        next_at = started
        while loop.time() < end:
            if traffic.rng.random() < 0.7 or not secret:
                if ready:
                    conv = ready.popleft()
                else:
                    kind, steps = traffic.conversation()
                    conv = {"kind": kind, "steps": steps, "rng": traffic.rng}
                    stats.flows[f"{kind}:started"] += 1
                task = asyncio.create_task(web_turn(client, conv, stats, ready))
            else:
                task = asyncio.create_task(wa_post(client, traffic, stats, secret))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            next_at += interval
            await asyncio.sleep(max(0.0, next_at - loop.time()))
        offered_seconds = loop.time() - started
        if tasks:
            await asyncio.wait(tasks, timeout=60)
        # Let the worker drain the inbox, then take the server's final view.
        drain_start = time.time()
        drained = None
        for _ in range(120):
            r = await client.get("/admin/timing", auth=auth)
            if r.json()["inbox"]["counts"].get("new", 0) == 0:
                drained = round(time.time() - drain_start, 1)
                break
            await asyncio.sleep(1)
        final = (await client.get("/admin/timing", auth=auth)).json()
        stop.set()
        await sampling
    return stats, series, final, offered_seconds, drained


def memory_trend(rss):
    """MB per minute over the run, after the first minute of warm-up."""
    points = [(t / 60, mb) for t, mb, _ in rss if t >= 60 and mb is not None]
    if len(points) < 3:
        return None
    xs, ys = zip(*points)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom, 2) if denom else None


def report(args, stats, series, final, offered_seconds, drained):
    total = sum(len(v) for v in stats.latency.values())
    client = {k: {"count": len(v), "p50_ms": round(pct(v, 50), 1), "p95_ms": round(pct(v, 95), 1),
                  "p99_ms": round(pct(v, 99), 1), "max_ms": round(max(v), 1) if v else 0.0}
              for k, v in stats.latency.items()}
    rss = [mb for _, mb, _ in series["rss"] if mb is not None]
    return {
        "config": {"rate": args.rate, "minutes": args.minutes, "seed": args.seed,
                   "fake_latency_ms": args.fake_latency_ms, "shadow": args.shadow,
                   "target": args.url or "spawned uvicorn, one worker"},
        "achieved_rate": round(total / offered_seconds, 2) if offered_seconds else 0,
        "client": client,
        "client_over_150ms": {k: {"count": len(v), "in_first_30s": sum(1 for t, _ in v if t < 30),
                                  "first": v[:10]} for k, v in stats.slow.items()},
        "status": dict(stats.status),
        "errors": dict(stats.errors),
        "flows": dict(stats.flows),
        "wa_sent": dict(stats.sent),
        "server": final["timings"],
        "inbox_final": final["inbox"],
        "process_final": final["process"],
        "queue_age_max_s": max((q for _, q, _ in series["queue"]), default=0.0),
        "queue_depth_max": max((n for _, _, n in series["queue"]), default=0),
        "drain_seconds": drained,
        "rss_series": series["rss"],
        "rss_first_last_mb": [rss[0], rss[-1]] if rss else None,
        "rss_trend_mb_per_min_after_warmup": memory_trend(series["rss"]),
    }


def main():
    parser = argparse.ArgumentParser(description="P9 load and soak test")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--spawn", action="store_true", help="start a local uvicorn to test")
    target.add_argument("--url", help="a running server, e.g. staging")
    parser.add_argument("--rate", type=float, default=20.0, help="requests per second")
    parser.add_argument("--minutes", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--admin-user")
    parser.add_argument("--admin-password")
    parser.add_argument("--wa-secret", help="the server's WA_APP_SECRET (--url only)")
    parser.add_argument("--fake-latency-ms", type=int, default=0)
    parser.add_argument("--shadow", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    proc = None
    if args.spawn:
        proc, base, data = spawn(args)
        auth, secret = SPAWN_ADMIN, SPAWN_SECRET
        print(f"server: {base} (pid {proc.pid}), data in {data}")
    else:
        if args.fake_latency_ms or args.shadow:
            parser.error("--fake-latency-ms and --shadow need --spawn")
        base, auth, secret = args.url.rstrip("/"), (args.admin_user, args.admin_password), args.wa_secret
        if not secret:
            print("no --wa-secret: sending /chat traffic only")
    try:
        result = report(args, *asyncio.run(run(args, base, auth, secret)))
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=30)
    text = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"written: {args.out}")
    print(text)


if __name__ == "__main__":
    main()
