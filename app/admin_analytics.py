"""Built-in analytics dashboard (behind the admin login).

GET /admin/analytics?from=YYYY-MM-DD&to=YYYY-MM-DD&channel=whatsapp
GET /admin/analytics.csv  (same filters) the aggregate numbers as CSV

The numbers come from admin.analytics, which uses admin.report's own
functions, so the dashboard and the weekly report agree. Counts only: no
name, phone number, session id or transcript (individual cases stay in
/admin/cases and Jira). Rendered on the server with inline SVG and CSS: no
script, no external asset, no tracker and no cookie, and a strict CSP.
"""

import datetime as dt
import html

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from admin import analytics
from admin.report import _fmt

from . import health as health_checks
from .adminauth import require_admin
from .timing import timings

api = APIRouter(dependencies=[Depends(require_admin)])

HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
CHANNEL_NAMES = {"web": "Website", "whatsapp": "WhatsApp", "messenger": "Messenger"}
# Categorical slots 1-3 of the validated default palette (dataviz skill),
# assigned per channel and never by rank, so a filter never repaints them.
CHANNEL_SLOT = {"web": 1, "whatsapp": 2, "messenger": 3}
TIMING_GROUPS = ("/chat", "/webhooks/whatsapp", "/webhooks/messenger", "worker:whatsapp", "worker:messenger")


def _window(request: Request) -> analytics.Window:
    q = request.query_params
    return analytics.parse_window(q.get("from"), q.get("to"), q.get("channel"))


@api.get("/admin/analytics.csv")
def analytics_csv(request: Request):
    window = _window(request)
    data = analytics.build(window)
    name = f"chatbot-analytics_{window.start}_{window.end}_{data['window']['channel']}.csv"
    return Response(
        analytics.to_csv(data),
        media_type="text/csv; charset=utf-8",
        headers={**HEADERS, "Content-Disposition": f'attachment; filename="{name}"'},
    )


@api.get("/admin/analytics", response_class=HTMLResponse)
def analytics_page(request: Request):
    window = _window(request)
    data = analytics.build(window)
    return HTMLResponse(render(window, data, _live_health()), headers=HEADERS)


def _live_health() -> dict:
    """The current /health checks and the server's own response times.
    Right now, not the date range: both live in this process."""
    try:
        checks = health_checks.checks()
    except health_checks.ChecksBroken as broken:
        checks = broken.checks
    except Exception:
        checks = {}
    summary = timings.summary()
    return {
        "checks": {name: bool(c.get("ok")) for name, c in checks.items()},
        "timings": {g: summary[g] for g in TIMING_GROUPS if g in summary},
        "since": dt.datetime.fromtimestamp(timings.since, dt.timezone.utc),
    }


# --- Rendering -----------------------------------------------------------------------------

e = html.escape


def _name(channel: str) -> str:
    return CHANNEL_NAMES.get(channel, channel)


def _qs(window: analytics.Window, **over) -> str:
    params = {"from": window.start.isoformat(), "to": window.end.isoformat(),
              "channel": window.channel or ""}
    params.update(over)
    return "&amp;".join(f"{k}={e(str(v))}" for k, v in params.items() if v)


def _tile(label: str, value: str, note: str = "") -> str:
    note_html = f"<span class='note'>{e(note)}</span>" if note else ""
    return f"<div class='tile'><span class='label'>{e(label)}</span><span class='value'>{e(value)}</span>{note_html}</div>"


def _table(header: list[str], rows: list[list], caption: str = "", numeric_from: int = 1) -> str:
    head = "".join(f"<th scope='col'{' class=num' if i >= numeric_from else ''}>{e(h)}</th>"
                   for i, h in enumerate(header))
    body = "".join(
        "<tr>" + "".join(
            f"<th scope='row'>{e(str(c))}</th>" if i == 0 else
            f"<td{' class=num' if i >= numeric_from else ''}>{e(str(c))}</td>"
            for i, c in enumerate(row)
        ) + "</tr>"
        for row in rows
    ) or f"<tr><td colspan='{len(header)}' class='empty'>Nothing in this range.</td></tr>"
    cap = f"<caption>{e(caption)}</caption>" if caption else ""
    return f"<table>{cap}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _bars(items: list[tuple[str, int]], total: int | None = None) -> str:
    """A labelled horizontal bar list (one series: no legend, values printed)."""
    if not items:
        return "<p class='empty'>Nothing in this range.</p>"
    top = max(v for _, v in items) or 1
    rows = []
    for label, value in items:
        share = f" · {_fmt(value / total, 'pct')}" if total else ""
        width = 0 if not value else max(1.0, 100 * value / top)
        rows.append(
            f"<div class='bar-row' title='{e(label)}: {value:,}{share}'>"
            f"<span class='bar-label'>{e(label)}</span>"
            f"<span class='bar-track'><span class='bar' style='width:{width:.1f}%'></span></span>"
            f"<span class='bar-value'>{value:,}{e(share)}</span></div>"
        )
    return "<div class='bars'>" + "".join(rows) + "</div>"


def _daily_chart(daily: list[dict], channels: list[str]) -> str:
    """Conversations per day, stacked by channel, as inline SVG."""
    totals = [sum(d["conv"].get(c, 0) for c in channels) for d in daily]
    peak = max(totals, default=0)
    if not peak:
        return "<p class='empty'>No conversations in this range.</p>"
    width, height, left, bottom, top_pad = 720, 220, 44, 24, 8
    plot_w, plot_h = width - left - 8, height - bottom - top_pad
    slot = plot_w / len(daily)
    bar_w = max(2.0, min(28.0, slot * 0.7))
    scale = plot_h / peak
    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-labelledby='daily-title' class='chart'>",
        "<title id='daily-title'>Conversations per day by channel</title>",
    ]
    for frac in (0, 0.5, 1):
        y = top_pad + plot_h - frac * plot_h
        parts.append(f"<line x1='{left}' x2='{width - 8}' y1='{y:.1f}' y2='{y:.1f}' class='grid'/>")
        parts.append(f"<text x='{left - 6}' y='{y + 4:.1f}' class='axis' text-anchor='end'>{round(peak * frac):,}</text>")
    label_every = max(1, len(daily) // 8)
    for i, (day, total) in enumerate(zip(daily, totals)):
        x = left + i * slot + (slot - bar_w) / 2
        y = top_pad + plot_h
        stack = [(c, day["conv"].get(c, 0)) for c in channels if day["conv"].get(c, 0)]
        for j, (channel, value) in enumerate(stack):
            h = value * scale
            y -= h
            gap = 2 if j < len(stack) - 1 else 0  # 2px surface gap between segments
            parts.append(
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_w:.1f}' height='{max(0.5, h - gap):.1f}' "
                f"class='s{CHANNEL_SLOT.get(channel, 1)}' rx='{2 if j == len(stack) - 1 else 0}'>"
                f"<title>{e(day['date'])} · {e(_name(channel))}: {value:,}</title></rect>"
            )
        if i % label_every == 0:
            label = dt.date.fromisoformat(day["date"]).strftime("%d/%m")
            parts.append(f"<text x='{x + bar_w / 2:.1f}' y='{height - 6}' class='axis' text-anchor='middle'>{label}</text>")
    parts.append("</svg>")
    legend = "".join(
        f"<span class='key'><span class='swatch s{CHANNEL_SLOT.get(c, 1)}'></span>{e(_name(c))}</span>"
        for c in channels
    ) if len(channels) > 1 else ""
    return (f"<div class='legend'>{legend}</div>" if legend else "") + "".join(parts)


def _pct(value) -> str:
    return _fmt(value, "pct")


def _section(anchor: str, title: str, intro: str, body: str) -> str:
    return (f"<section id='{anchor}' aria-labelledby='{anchor}-h'><h2 id='{anchor}-h'>{e(title)}</h2>"
            f"<p class='intro'>{e(intro)}</p>{body}</section>")


def _traffic(data) -> str:
    tr, channels = data["traffic"], data["channels"]
    tot = tr["totals"]
    tiles = "".join([
        _tile("Conversations", _fmt(tot["conversations"], "int")),
        _tile("Customer messages", _fmt(tot["customer_messages"], "int")),
        _tile("Bot messages", _fmt(tot["bot_messages"], "int"), "not counting the welcome"),
        _tile("Bot messages per conversation", _fmt(tot["bot_per_conversation"], "ratio"), "launch target ≤ 4"),
    ])
    by_channel = _table(
        ["Channel", "Conversations", "Customer messages", "Bot messages", "Bot per conversation"],
        [[_name(c), _fmt(v["conversations"], "int"), _fmt(v["customer_messages"], "int"),
          _fmt(v["bot_messages"], "int"), _fmt(v["bot_per_conversation"], "ratio")]
         for c, v in tr["by_channel"].items()],
    )
    daily_rows = [
        [d["date"]] + [f"{d['conv'].get(c, 0):,}" for c in channels]
        + [f"{sum(d['user'].values()):,}", f"{sum(d['bot'].values()):,}"]
        for d in tr["daily"]
    ]
    daily_table = _table(["Day (Lusaka)"] + [f"Conversations: {_name(c)}" for c in channels]
                         + ["Customer messages", "Bot messages"], daily_rows)
    body = (f"<div class='tiles'>{tiles}</div><div class='card'><h3>Conversations per day</h3>"
            f"{_daily_chart(tr['daily'], channels)}<details><summary>Show as a table</summary>{daily_table}</details></div>"
            f"<div class='card'><h3>By channel</h3>{by_channel}</div>")
    return _section("traffic", "Traffic",
                    "On WhatsApp and Messenger a session lasts across visits, so a “conversation” there "
                    "is a customer active in the range.", body)


OUTCOME_LABELS = {"answered": "Answered", "suggested": "Suggested (did you mean…)",
                  "not_understood": "Not understood", "out_of_scope": "Out of scope"}


def _understanding(data) -> str:
    u = data["understanding"]
    total = u["typed_total"]
    outcomes = _bars([(OUTCOME_LABELS[k], v) for k, v in u["typed_outcomes"].items()], total)
    intents = _table(["Intent", "Answers", "Typed", "Tapped"],
                     [[i["intent"], f"{i['total']:,}", f"{i['typed']:,}", f"{i['tapped']:,}"] for i in u["top_intents"]])
    r = u["repairs"]
    repairs = _table(["Repair", "Count"], [
        ["Two-strike handoff offers", r["two_strike_offers"]], ["Repeat", r["repeat"]],
        ["Clarify", r["clarify"]], ["Frustration", r["frustration"]],
        ["Context carried over", r["context_boosts"]], ["Two questions answered at once", r["two_questions_answered"]],
    ])
    unmatched = _table(["Message (masked)", "Count"], [[x["text"], x["count"]] for x in u["unmatched"]])
    if u["unmatched_withheld"]:
        unmatched += f"<p class='note'>{u['unmatched_withheld']:,} more withheld because they looked personal.</p>"
    body = (
        f"<div class='tiles'>{_tile('Typed messages the matcher handled', _fmt(total, 'int'))}"
        f"{_tile('Fallback rate', _pct(u['fallback_rate']), 'not understood ÷ customer messages')}</div>"
        f"<div class='grid2'><div class='card'><h3>What happened to typed questions</h3>{outcomes}</div>"
        f"<div class='card'><h3>Repairs</h3>{repairs}</div></div>"
        f"<div class='grid2'><div class='card'><h3>Top answers</h3>{intents}</div>"
        f"<div class='card'><h3>Most common questions the bot didn't understand</h3>"
        f"<p class='note'>Feed these back into the intent phrases.</p>{unmatched}</div></div>"
    )
    return _section("understanding", "Understanding",
                    "Typed questions only; a button tap always gets its answer. Answers include typed and tapped.", body)


def _minutes(v) -> str:
    return "—" if v is None else f"{v:,.1f} min"


def _safety(data) -> str:
    s = data["safety"]
    rep = s["reports"]
    tiles = "".join([
        _tile("Fraud reports", _fmt(rep["fraud"], "int")),
        _tile("Lost or stolen cards", _fmt(rep["lost_card"], "int")),
        _tile("Complaints", _fmt(rep["complaint"], "int")),
        _tile("Report questions declined", _fmt(s["urgent_confirmations_declined"], "int"),
              f"of {s['urgent_confirmations_asked']:,} “is this a report?” questions"),
    ])
    speed = _table(["Ticket", "Tickets timed", "Median", "90th percentile"], [
        [kind.capitalize(), f"{v['n']:,}", _minutes(v["median_minutes"]), _minutes(v["p90_minutes"])]
        for kind, v in s["time_to_raise"].items()
    ])
    types = _bars([(k.capitalize(), v) for k, v in s["tickets_by_type"].items()], sum(s["tickets_by_type"].values()))
    body = (f"<div class='tiles'>{tiles}</div><div class='grid2'>"
            f"<div class='card'><h3>How fast reports were raised</h3>"
            f"<p class='note'>From the start of the customer's visit to the ticket.</p>{speed}</div>"
            f"<div class='card'><h3>Tickets by type</h3>{types}</div></div>")
    return _section("safety", "Safety", "Every fraud report and complaint ends in a ticket that only a person closes.", body)


PICKUP_NAMES = {"callback": "Callbacks", "complaint": "Complaints", "handoff": "Hand-offs", "fraud": "Fraud reports"}


def _people(data) -> str:
    p = data["people"]
    c = p["csat"]
    tiles = "".join([
        _tile("“Talk to a person” requests", _fmt(p["talk_to_a_person"], "int")),
        _tile("Callback requests", _fmt(p["callbacks"], "int")),
        _tile("Hand-off tickets", _fmt(p["handoff_tickets"], "int"), "WhatsApp and Messenger"),
        _tile("CSAT", "—" if c["score"] is None else f"{c['score']:.2f} / 5", "launch target ≥ 4.2"),
    ])
    hours_table = _table(["Ticket", "Total", "Out of hours", "Share"], [
        [PICKUP_NAMES[k], f"{v['total']:,}", f"{v['out_of_hours']:,}", _pct(v["share"])]
        for k, v in p["out_of_hours"].items()
    ])
    csat = _table(["Feedback", "Count"], [
        ["Asked", f"{c['asked']:,}"], ["Good", f"{c['up']:,}"], ["Not good", f"{c['down']:,}"],
        ["Response rate", _pct(c["response_rate"])],
    ])
    body = (f"<div class='tiles'>{tiles}</div><div class='grid2'>"
            f"<div class='card'><h3>Raised outside contact-centre hours</h3>{hours_table}</div>"
            f"<div class='card'><h3>Customer feedback (sampled)</h3>{csat}"
            f"<p class='note'>{p['two_strike_offers']:,} offers of a person after two misunderstandings; "
            f"{p['paused_messages']:,} messages arrived while a person had the conversation.</p></div></div>")
    return _section("people", "People", "Hand-offs to the contact centre, callbacks and feedback.", body)


CONSENT_NAMES = {"yes": "Yes", "no": "No", "not asked": "Not asked", "unknown": "Not recorded"}


def _marketing(data) -> str:
    m = data["marketing"]
    tiles = "".join([
        _tile("Leads (callback requests)", _fmt(m["callbacks"], "int")),
        _tile("Marketing consent rate", _pct(m["consent_rate"]), "yes ÷ all callbacks"),
        _tile("Marketing opt-outs", _fmt(m["opt_outs"], "int")),
    ])
    consent = _bars([(CONSENT_NAMES[k], v) for k, v in m["consent"].items()], m["callbacks"])
    topics = _bars([(t["topic"], t["callbacks"]) for t in m["topics"]], m["callbacks"])
    campaigns = _table(["Source", "Sessions", "Callbacks", "With consent"], [
        [x["source"], f"{x['sessions']:,}", f"{x['callbacks']:,}", f"{x['consenting_callbacks']:,}"]
        for x in m["campaigns"]
    ])
    body = (f"<div class='tiles'>{tiles}</div><div class='grid2'>"
            f"<div class='card'><h3>Consent on callbacks</h3>{consent}</div>"
            f"<div class='card'><h3>What leads asked about</h3>{topics}</div></div>"
            f"<div class='card'><h3>Campaign and QR-code sources</h3>{campaigns}</div>")
    return _section("marketing", "Marketing",
                    "Names and phone numbers are never shown here; they are on the tickets for the contact centre.", body)


def _health(data, live) -> str:
    h = data["health"]
    tiles = "".join([
        _tile("Delivery failures", _fmt(h["delivery_failures"], "int"), "WhatsApp and Messenger"),
        _tile("Delivery failure rate", _pct(h["delivery_failure_rate"]), "launch target ≤ 1%"),
        _tile("Rate-limited visitors", _fmt(h["rate_limited"], "int")),
        _tile("Jira pushes given up", _fmt(h["jira_push_abandoned"], "int")),
    ])
    checks = "".join(
        f"<li class='{'ok' if ok else 'bad'}'><span aria-hidden='true'>{'✓' if ok else '✕'}</span> "
        f"{e(name.replace('_', ' '))}: <strong>{'OK' if ok else 'Failing'}</strong></li>"
        for name, ok in live["checks"].items()
    ) or "<li>Checks unavailable.</li>"
    times = _table(["Route", "Requests", "p50", "p95", "p99"], [
        [g, f"{t['count']:,}", f"{t['p50_ms']:,.0f} ms", f"{t['p95_ms']:,.0f} ms", f"{t['p99_ms']:,.0f} ms"]
        for g, t in live["timings"].items()
    ])
    body = (f"<div class='tiles'>{tiles}</div><div class='grid2'>"
            f"<div class='card'><h3>Health checks right now</h3><ul class='checks'>{checks}</ul></div>"
            f"<div class='card'><h3>Response times</h3><p class='note'>Since the server started "
            f"({live['since']:%d/%m/%Y %H:%M} UTC), not the date range.</p>{times}</div></div>")
    return _section("health", "Health", "Delivery, limits and integrations in the date range, plus the live checks.", body)


def _filters(window: analytics.Window) -> str:
    today = analytics.lusaka_today()
    presets = "".join(
        f"<a href='?{_qs(analytics.preset(d, today), channel=window.channel or '')}'"
        f"{' aria-current=true' if window.days == d and window.end == today else ''}>Last {d} days</a>"
        for d in analytics.PRESETS
    )
    options = "".join(
        f"<option value='{v}'{' selected' if (window.channel or '') == v else ''}>{e(label)}</option>"
        for v, label in [("", "All channels")] + [(c, _name(c)) for c in CHANNEL_NAMES]
    )
    return (
        "<form class='filters' method='get' action='/admin/analytics'>"
        f"<nav class='presets' aria-label='Date presets'>{presets}</nav>"
        f"<label>From <input type='date' name='from' value='{window.start}' max='{today}'></label>"
        f"<label>To <input type='date' name='to' value='{window.end}' max='{today}'></label>"
        f"<label>Channel <select name='channel'>{options}</select></label>"
        "<button type='submit'>Apply</button>"
        f"<a class='csv' href='/admin/analytics.csv?{_qs(window)}'>Download CSV</a></form>"
    )


STYLE = """
:root{color-scheme:light;--surface-0:#f6f5f2;--surface-1:#fcfcfb;--border:#dedcd6;--text-primary:#0b0b0b;
--text-secondary:#52514e;--text-muted:#6f6e69;--accent:#256abf;--series-1:#2a78d6;--series-2:#eb6834;
--series-3:#1baf7a;--good:#0b7a3b;--bad:#b3261e;--grid:#e8e6e1}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--surface-0:#121211;
--surface-1:#1a1a19;--border:#383835;--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#9d9c93;
--accent:#6da7ec;--series-1:#3987e5;--series-2:#d95926;--series-3:#199e70;--good:#5cc98a;--bad:#f2766c;--grid:#2c2c2a}}
:root[data-theme="dark"]{color-scheme:dark;--surface-0:#121211;--surface-1:#1a1a19;--border:#383835;
--text-primary:#fff;--text-secondary:#c3c2b7;--text-muted:#9d9c93;--accent:#6da7ec;--series-1:#3987e5;
--series-2:#d95926;--series-3:#199e70;--good:#5cc98a;--bad:#f2766c;--grid:#2c2c2a}
*{box-sizing:border-box}
body{margin:0;background:var(--surface-0);color:var(--text-primary);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header,main{max-width:1180px;margin:0 auto;padding:0 16px}
header{padding-top:24px}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.2rem;margin:32px 0 4px}h3{font-size:1rem;margin:0 0 10px}
.sub,.intro,.note{color:var(--text-secondary)}.note{font-size:.85rem;margin:6px 0}
a{color:var(--accent)}nav.sections{display:flex;gap:14px;flex-wrap:wrap;margin:10px 0 0}
.filters{position:sticky;top:0;z-index:1;display:flex;flex-wrap:wrap;gap:10px 16px;align-items:end;
background:var(--surface-0);padding:12px 0;border-bottom:1px solid var(--border)}
.presets{display:flex;gap:6px}.presets a{padding:5px 10px;border:1px solid var(--border);border-radius:6px;
text-decoration:none;color:var(--text-primary);background:var(--surface-1)}.presets a[aria-current]{font-weight:700;border-color:var(--accent)}
label{display:flex;flex-direction:column;font-size:.8rem;color:var(--text-secondary);gap:2px}
input,select,button{font:inherit;padding:5px 8px;border:1px solid var(--border);border-radius:6px;background:var(--surface-1);color:var(--text-primary)}
button{background:var(--accent);border-color:var(--accent);color:#fff;cursor:pointer}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(190px,100%),1fr));gap:12px;margin:12px 0}
.tile,.card{background:var(--surface-1);border:1px solid var(--border);border-radius:10px;padding:14px}
.tile{display:flex;flex-direction:column;gap:2px}.tile .label{color:var(--text-secondary);font-size:.85rem}
.tile .value{font-size:1.6rem;font-weight:650;font-variant-numeric:tabular-nums}
.card{margin:12px 0;overflow-x:auto}.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(340px,100%),1fr));gap:0 12px}
table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)}
thead th{color:var(--text-secondary);font-weight:600}.num{text-align:right;font-variant-numeric:tabular-nums}
tbody th{font-weight:400;overflow-wrap:anywhere}.empty{color:var(--text-muted)}
.bars{display:flex;flex-direction:column;gap:8px}.bar-row{display:grid;grid-template-columns:minmax(120px,38%) 1fr auto;gap:10px;align-items:center}
.bar-label{font-size:.9rem;overflow-wrap:anywhere}.bar-track{height:12px}.bar{display:block;height:12px;background:var(--series-1);border-radius:0 4px 4px 0}
.bar-value{font-variant-numeric:tabular-nums;font-size:.9rem;color:var(--text-secondary);white-space:nowrap}
.chart{width:100%;height:auto;display:block}.chart .grid{stroke:var(--grid);stroke-width:1}
.chart .axis{fill:var(--text-muted);font-size:11px}.chart rect:hover{opacity:.8}
.s1{fill:var(--series-1);background:var(--series-1)}.s2{fill:var(--series-2);background:var(--series-2)}.s3{fill:var(--series-3);background:var(--series-3)}
.legend{display:flex;gap:14px;margin-bottom:6px;font-size:.85rem;color:var(--text-secondary)}
.key{display:inline-flex;align-items:center;gap:6px}.swatch{display:inline-block;width:12px;height:12px;border-radius:3px}
details{margin-top:10px}summary{cursor:pointer;color:var(--accent)}
.checks{list-style:none;padding:0;margin:0;columns:2}.checks li{padding:3px 0}.checks .ok span{color:var(--good)}.checks .bad{color:var(--bad)}
footer{max-width:1180px;margin:32px auto;padding:0 16px;color:var(--text-muted);font-size:.8rem}
@media (max-width:600px){.grid2{grid-template-columns:1fr}.checks{columns:1}.bar-row{grid-template-columns:1fr auto}.bar-track{grid-column:1/-1;order:3}}
"""


def render(window: analytics.Window, data: dict, live: dict) -> str:
    scope = "all channels" if not window.channel else _name(window.channel)
    sections = [("traffic", "Traffic"), ("understanding", "Understanding"), ("safety", "Safety"),
                ("people", "People"), ("marketing", "Marketing"), ("health", "Health")]
    nav = "".join(f"<a href='#{a}'>{t}</a>" for a, t in sections)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>Chatbot analytics</title><style>{STYLE}</style></head><body>
<header><h1>Chatbot analytics</h1>
<p class="sub">{window.start:%d/%m/%Y} to {window.end:%d/%m/%Y} (Lusaka days, {window.days} days), {e(scope)}.
Counts only: individual cases are in <a href="/admin/cases">Cases</a> and Jira. Draft figures: check them before they
go into a management report.</p><nav class="sections" aria-label="Sections">{nav}</nav>
{_filters(window)}</header><main>
{_traffic(data)}{_understanding(data)}{_safety(data)}{_people(data)}{_marketing(data)}{_health(data, live)}
</main><footer>Same calculations as the weekly report (<code>python -m admin.report</code>). Self-hosted: no
outside tracker, no cookies.</footer></body></html>"""
