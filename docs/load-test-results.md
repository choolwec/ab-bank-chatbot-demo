# Load and soak test results (P9)

**Summary.** This is a **local run only**: 20 requests/s for 5 minutes (not
30) against one uvicorn worker on a development container, with WhatsApp and
Jira in mock mode. It is not a staging or production result. The 30-minute
runs on staging and on the Lusaka VM are **still to do**; they wait for the VM
(P7).

- **Latency: target met locally.** The server's own p95 was 18.9 ms on
  `/chat`, 4.3 ms on the WhatsApp webhook and 20.1 ms per webhook message in
  the worker, against a target of 150 ms. All 6,000 requests returned 200.
  Every fraud and callback conversation ended with a ticket reference. The
  inbox never backed up.
- **Memory: no growth seen, but 5 minutes cannot prove it.** RSS rose from
  150 MB to 349 MB in the first 30 seconds, as the models loaded on first
  use. It then crept up 0.8 MB a minute to 354 MB. The Python-level growth
  comes from two structures that are capped by design. The 30-minute soak
  will show whether RSS flattens.
- **Two production risks, found by adding a fake 250 ms network delay:**
  1. Each real Jira push ran inside the customer's `/chat` request, so
     `/chat` p95 rose to 322 ms. **Fixed:** the push now runs in the
     background, and p95 went back to 19 ms.
  2. The single WhatsApp worker sends one message at a time. At 250 ms per
     Graph API call it manages about 1.6 messages/s, while this load offers
     about 5.4, so the queue grew by about 4 messages a second. **Not fixed**
     (section 5).

---

## 1. Set-up

| | |
|---|---|
| Date | 24/09/2026 |
| Code | branch `wip/deploy` (P7/P9), all tests green |
| Machine | Development container, 4 vCPU (Intel Xeon 2.1 GHz), 16 GB RAM. The VM target is 2 vCPU and 4 GB, so these numbers are optimistic for CPU. The app is one process and mostly uses one core. |
| Server | `uvicorn app.main:app --workers 1`, SQLite session store (the default), a fresh data directory, the embedding model present (so the N7 urgent model runs, as in production), `EMBEDDINGS_ENABLED` off |
| Integrations | WhatsApp sends and Jira in mock mode (local files), except in section 4 |
| Load | `python research/load/load.py --spawn --rate 20 --minutes 5` |
| Mix | 70% `/chat` turns from real paths: FAQ questions from the held-out evaluation set (10% out of scope) with a button tap; the four-message fraud report (C8); the callback request (C7). 30% signed WhatsApp webhook posts built from `tests/data/wa/*.json` with fresh message ids, from 200 synthetic customers: text 60%, button and list replies 10% each, delivery statuses 10%, images and locations 5% each. |
| Arrival | Open loop: a request every 50 ms however slow the server is. The widget's "open" call counts as a request. |
| Raw results | `research/load/results/*.json` |

## 2. Results: 20 requests/s for 5 minutes

| Measure | Client p50 | Client p95 | Server p50 | Server p95 | Server p99 | Server max |
|---|---|---|---|---|---|---|
| `/chat` (4,215 requests) | 10.3 ms | 22.1 ms | 7.5 ms | **18.9 ms** | 29.1 ms | 546 ms |
| `/webhooks/whatsapp` (1,785) | 5.0 ms | 7.8 ms | 2.4 ms | **4.3 ms** | 7.6 ms | 149 ms |
| Worker, per WhatsApp message (1,615) | | | 13.4 ms | **20.1 ms** | 31.9 ms | 583 ms |

- Achieved rate: 20.0 requests/s. Status codes: all 200. Client errors: none.
- Only 6 of 6,000 requests took over 150 ms at the client. Five came in the
  first 3 seconds, as the models loaded on first use; the other took 211 ms,
  160 s into the run.
- Flows: all 168 fraud reports and all 182 callback requests ended with a
  ticket reference in the reply, along with 568 FAQ conversations.
- Inbox: the oldest waiting message was never older than 0.03 s, and the
  queue was at most 1 deep. All 1,615 messages were processed by the end;
  delivery statuses are logged, not queued.
- An earlier identical run gave the same picture (`/chat` p95 18.2 ms,
  worker p95 20.3 ms).

## 3. Memory

| Seconds | 0 | 30 | 60 | 95 | 125 | 160 | 190 | 220 | 250 | 285 |
|---|---|---|---|---|---|---|---|---|---|---|
| RSS (MB) | 149.5 | 348.5 | 350.5 | 350.9 | 351.1 | 351.5 | 352.1 | 352.2 | 352.9 | 353.5 |
| Session locks | 1 | 197 | 335 | 465 | 573 | 687 | 778 | 869 | 962 | 1,069 |

After the first minute, RSS grew about 0.8 MB a minute (1.6 in the earlier
run). An in-process profile (`tracemalloc`, 1,500 conversations after
warm-up) found only 0.7 MB of Python-level growth, from three places:

- the session store's per-key locks, pruned once there are 10,000;
- the timing windows behind `/admin/timing`, at most 20,000 samples per route;
- the key strings of those locks.

All three have a fixed ceiling, of a few MB in total. The rest of the RSS
growth is most likely the allocator keeping freed memory, which levels off;
the 30-minute soak will show whether it does. **Verdict: no growth seen yet, not yet proven.**

Steady-state memory is about 350 MB. That fits the VM's 4 GB easily. It
also fits Render's free plan (512 MB [VERIFY: Render's current free-plan
memory]) with about 150 MB to spare, including shadow mode (section 6).

## 4. With real network round trips (fake 250 ms upstream)

Mock mode hides network time. `load.py --fake-latency-ms 250` points the
WhatsApp sender and Jira at a local fake server that answers every request
after 250 ms. 250 ms is an **assumption**, not a measurement from Lusaka;
measure the real figure from the VM. Each run lasted 2 minutes at 20
requests/s.

| | Before the fix | After the fix |
|---|---|---|
| `/chat` server p50 / p95 | 7.0 / **322 ms** | 6.5 / **19.1 ms** |
| Worker per message, p50 / p95 | 632 / 691 ms | 631 / 674 ms |
| Inbox 2 minutes after the load stopped | 247 waiting, oldest 168 s | 248 waiting, oldest 168 s |
| Deepest queue seen | 438 | 438 |

**Jira (fixed).** `audit.create_ticket()` called Jira inside the request, so
every turn that created a ticket waited for the round trip. That is about 8%
of `/chat` turns in this mix, which is enough to move p95. With real
credentials the push now runs in a background thread. The ticket is already
in SQLite by then, so the push stays best-effort, exactly as before. Mock mode
still writes inline. Tests: `tests/test_jira_export.py`.

**The WhatsApp worker (not fixed).** Each message needs about 2.5 Graph calls
(read receipt and typing indicator, then the reply), one after another.
Messages are processed one at a time, which keeps each customer's messages in
order (W2). At 250 ms per call, that is about 630 ms a message, or about 1.6
messages/s (95 a minute). This load offers about 5.4 messages/s, so the queue
grew steadily, and the oldest message aged about 0.7 s for every second of
load. After about 14 minutes of such load it would pass
`STALE_MESSAGE_MINUTES` (10), and customers would start getting the
stale-message apology instead of an answer.

## 5. What to do about the worker

This is a capacity limit, not a bug, and the fix changes W2's design, so it
is written up rather than made here.

- **Measure first.** Run `load.py --url` against the VM with real Graph
  latency and a WhatsApp rate like the pilot's. [CONFIRM: expected WhatsApp
  messages per minute at peak, PO] If the pilot peak stays well under about
  90 messages a minute, the single worker is enough for the pilot.
- **Then, if needed,** process different customers in parallel while keeping
  each customer's messages in order. For example, a small pool (4 to 8
  threads) in which each customer's rows always go to the same thread, keyed
  by `user_hash`. The per-key session locks already make this safe for
  sessions. Also consider sending the read receipt without waiting for it.
- **Watch it** in production through R1's queue-age alert (over 2 minutes)
  and `/admin/timing`.

## 6. Shadow mode (the staging configuration)

`load.py --spawn --shadow` (`SHADOW_MATCHER=true`, as `render.yaml` now sets
for staging), 90 seconds at 20 requests/s:

| | Shadow off (section 2) | Shadow on |
|---|---|---|
| `/chat` server p95 | 18.9 ms | 26.6 ms |
| Worker p95 | 20.1 ms | 29.7 ms |
| RSS after 60 s | 350.5 MB | 344.3 MB |

Scoring every message with the hybrid matcher as well adds about 8 ms at p95
and no measurable memory, because the embedding model is already loaded for
the urgent check.

## 7. Things the plan said to watch

| Watch | Seen locally |
|---|---|
| SQLite lock contention between the worker and `/chat` | None: no errors, and `/chat` p99 29 ms while the worker ran alongside. |
| `SessionStore` per-key lock growth | 1,069 locks after 5 minutes, one per conversation, pruned at 10,000. `/admin/timing` shows the count. |
| Embedding latency with `EMBEDDINGS_ENABLED` | Not tested (off in production until the N4 reviews pass). Shadow mode, which runs the same hybrid matcher, adds about 8 ms at p95. |

## 8. Still to do

| Run | Where | When | Command |
|---|---|---|---|
| 30 min at 20 requests/s | Staging | When staging has admin credentials and a test WhatsApp app secret | `python research/load/load.py --url https://<staging> --admin-user … --admin-password … --wa-secret … --minutes 30` |
| 30 min at 20 requests/s | The Lusaka VM | After P7 acceptance, before M3 | the same, against the VM, outside business hours |
| Real Graph latency | The Lusaka VM | With the production run | from the VM: `curl -o /dev/null -s -w '%{time_total}\n' https://graph.facebook.com/` |

Pass criteria for both: server p95 at or under 150 ms on `/chat` and the
webhooks, the RSS series flat after warm-up, no errors, and the inbox queue
age under 2 minutes. The load script's WhatsApp traffic uses synthetic
numbers, and on a server with real Meta credentials it would try to send to
them. Run it on the VM only while `WA_ACCESS_TOKEN` is unset (mock mode), or
point `GRAPH_BASE_URL` at a stub for the run.
