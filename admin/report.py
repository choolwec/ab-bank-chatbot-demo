"""Weekly quality report (build plan §6, ticket H6).

Usage:  python -m admin.report --days 7 [--out data/report.md] [--stdout] [--skip-eval]

Writes data/report.md (or --out): every H6 line split by channel, the
excellence-plan §1 launch targets marked PASS / FAIL, a lead-generation
section for Marketing, and the top unmatched utterances -- still the single
biggest quality lever at this scale, since they become new intent phrasings
each week.

Traffic numbers come from audit `action` values and the tickets table (the
Source column says which). The accuracy targets come from the offline
evaluation (held-out set, BANKING77, the S1 red-team corpora), run now on the
production matcher; --skip-eval leaves them n/a.

No customer identity is ever printed: no session id, user_hash, name or phone
number. Free text (unmatched messages, callback topics, campaign sources) is
already masked in the audit log and gets the same second PII check as
admin.export_utterances; anything that still looks personal is withheld.
"""

import argparse
import collections
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

from admin.export_utterances import looks_personal
from app import audit, config

CHANNELS = ("web", "whatsapp", "messenger")
MESSAGING = ("whatsapp", "messenger")
UNMATCHED_SHOWN = 20
TOPICS_SHOWN = 10
# The WhatsApp free tier is per calendar month; the report prorates it.
DAYS_PER_MONTH = 30
REDTEAM_DIR = config.BASE_DIR / "tests" / "data"
PASS, FAIL, NA = "PASS", "FAIL", "n/a"
DASH = "—"

# Callback topics are grouped by the matcher's best guess at the intent
# category of what the customer typed.
TOPIC_GROUPS = {
    "accounts": "Accounts",
    "etumba": "eTumba",
    "fees": "Fees and charges",
    "loans": "Loans",
    "locations": "Branches and contact details",
    "technical": "App and service problems",
    "urgent": "Cards, fraud and complaints",
}
OTHER_TOPIC = "Other or unclear"


def _since(days: int) -> str:
    return (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    ).isoformat(timespec="seconds")


def _ratio(a, b):
    return a / b if b else None


# --- Reading the audit trail ---------------------------------------------------


class Traffic:
    """Counts per (name, channel) from the audit events in the window.

    Names: "conv" (distinct sessions with a customer message), "user", "bot"
    (bubbles, not counting the welcome), "turn:<action>" (bot turns: one
    turn logs one event per bubble, all with the same action),
    "sys:<action>" (system events), "shadow_agree", "template_sent".
    """

    def __init__(self) -> None:
        self.counts: collections.Counter = collections.Counter()
        self.channels = set(CHANNELS)

    def n(self, channel, *names) -> int:
        """Total over `names` for one channel (None = every channel); a name
        ending in "*" is a prefix ("turn:digression:*")."""
        total = 0
        for (name, ch), value in self.counts.items():
            if channel is not None and ch != channel:
                continue
            if any(name.startswith(k[:-1]) if k.endswith("*") else name == k for k in names):
                total += value
        return total

    def ordered_channels(self) -> list[str]:
        return list(CHANNELS) + sorted(self.channels - set(CHANNELS))

    # Derived lines, shared by the channel tables and the §1 targets.
    def strikes(self, ch) -> int:
        return self.n(ch, "turn:fallback", "turn:two_strike")

    def per_conversation(self, ch, value):
        return _ratio(value, self.n(ch, "conv"))

    def failures(self, ch) -> int:
        return self.n(ch, "sys:send_failed", "sys:wa_status:failed")

    def failure_rate(self, ch):
        """Failures ÷ bot messages, on WhatsApp and Messenger only (None for
        the web, which has no delivery receipts)."""
        if ch is not None and ch not in MESSAGING:
            return None
        channels = MESSAGING if ch is None else (ch,)
        return _ratio(sum(self.failures(c) for c in channels), sum(self.n(c, "bot") for c in channels))

    def csat_answers(self, ch) -> int:
        return self.n(ch, "turn:csat:up", "turn:csat:down")

    def csat_score(self, ch):
        """Thumbs-up share × 5, the §1 CSAT scale; None with no answers."""
        share = _ratio(self.n(ch, "turn:csat:up"), self.csat_answers(ch))
        return None if share is None else share * 5


def collect(con, since: str) -> Traffic:
    t = Traffic()
    conversations = collections.defaultdict(set)
    prev = None
    rows = con.execute(
        "SELECT session_id, role, action, channel, text FROM events WHERE ts >= ? "
        "ORDER BY session_id, id",
        (since,),
    )
    for session_id, role, action, channel, text in rows:
        ch = channel or "web"
        t.channels.add(ch)
        if role == "user":
            conversations[ch].add(session_id)
            t.counts["user", ch] += 1
        elif role == "bot":
            if action != "welcome":
                t.counts["bot", ch] += 1
            if action and prev != (session_id, "bot", action):
                t.counts["turn:" + action, ch] += 1
        elif action:
            t.counts["sys:" + action, ch] += 1
            if action == "shadow" and _shadow_agrees(text):
                t.counts["shadow_agree", ch] += 1
            if action.startswith("template:") and (text or "").rstrip().endswith("sent"):
                t.counts["template_sent", ch] += 1
        prev = (session_id, role, action)
    for ch, sessions in conversations.items():
        t.counts["conv", ch] = len(sessions)
    return t


def _shadow_agrees(text) -> bool:
    try:
        return bool(json.loads(text or "{}").get("agree"))
    except (ValueError, AttributeError):
        return False


def load_tickets(con, since: str) -> list[tuple[str, str, dict]]:
    out = []
    for kind, channel, raw in con.execute(
        "SELECT type, channel, fields FROM tickets WHERE created >= ?", (since,)
    ):
        try:
            fields = json.loads(raw or "{}")
        except ValueError:
            fields = {}
        out.append((kind, channel or "web", fields if isinstance(fields, dict) else {}))
    return out


def top_unmatched(con, since: str) -> tuple[list[tuple[str, int]], int]:
    """The most frequent unmatched messages, and how many distinct ones were
    withheld because they still look personal."""
    rows = con.execute(
        "SELECT lower(text), COUNT(*) AS n FROM events WHERE action='unmatched' "
        "AND ts >= ? GROUP BY lower(text) ORDER BY n DESC, lower(text)",
        (since,),
    ).fetchall()
    shown, withheld = [], 0
    for text, n in rows:
        if looks_personal(text or ""):
            withheld += 1
        elif len(shown) < UNMATCHED_SHOWN:
            shown.append((text, n))
    return shown, withheld


# --- Offline measurements (the §1 accuracy and safety targets) ------------------


def _lines(path: Path) -> list[str]:
    return [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def redteam_metrics(data_dir: Path = REDTEAM_DIR) -> dict:
    """S1 red-team corpora: positives the urgent scan catches (directly or
    after a "yes"), and everyday messages it would send straight into a
    report without asking (a hard signal)."""
    from app import guards

    pos, neg = data_dir / "urgent_positive.txt", data_dir / "urgent_negative.txt"
    if not pos.exists() or not neg.exists():
        return {}
    positives = [
        tuple(p.strip() for p in line.split("|", 1)) for line in _lines(pos) if "|" in line
    ]
    negatives = _lines(neg)
    caught = sum(
        1 for kind, text in positives if (s := guards.urgent_scan(text)) and s.kind == kind
    )
    hard = sum(1 for text in negatives if (s := guards.urgent_scan(text)) and s.is_hard)
    return {
        "redteam_caught": caught,
        "redteam_n": len(positives),
        "redteam_recall": _ratio(caught, len(positives)),
        "redteam_hard_false": hard,
        "redteam_neg_n": len(negatives),
    }


def offline_metrics() -> dict:
    """The eval-gate numbers on the production matcher, plus the red team."""
    from admin.eval_report import GATES_FILE, evaluate, load_gates
    from app.router import matcher

    result = evaluate(matcher)
    mode = getattr(matcher, "mode", "char")
    gates_file = GATES_FILE if mode == "char" else GATES_FILE.with_name("gates_embeddings.yaml")
    return {**result.metrics, **redteam_metrics(), "mode": mode, "gates": load_gates(gates_file)}


# --- Formatting ------------------------------------------------------------------


def _fmt(value, kind: str) -> str:
    if value is None:
        return DASH
    if kind == "int":
        return f"{value:,}"
    if kind == "pct":
        return f"{value:.1%}"
    if kind == "usd":
        return f"US$ {value:,.2f}"
    if kind == "usd4":
        return f"US$ {value:,.4f}"
    return f"{value:.2f}"


def status(value, op: str, target: float) -> str:
    """PASS / FAIL against a target; n/a when there is nothing to measure."""
    if value is None:
        return NA
    ok = value >= target if op == ">=" else value <= target
    return PASS if ok else FAIL


def _cell(text: str) -> str:
    """Customer free text made safe for a markdown table: no HTML (a viewer
    may render it), no pipe breaking the row, one line."""
    text = " ".join(str(text).split())
    for raw, safe in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ("|", "\\|"), ("`", "'")):
        text = text.replace(raw, safe)
    return text


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out


# --- The per-channel lines (H6 table) ---------------------------------------------


def _line_groups(t: Traffic):
    """(section, [(label, source, kind, fn(channel or None))]). fn returns
    None where the line doesn't apply (shown as a dash)."""
    n = t.n

    def count(*names):
        return lambda ch: n(ch, *names)

    return [
        ("Volume", [
            ("Conversations", "distinct `session_id` with a customer message", "int", count("conv")),
            ("Customer messages", "role `user`", "int", count("user")),
            ("Bot messages (not counting the welcome)", "role `bot`", "int", count("bot")),
            ("Bot messages per conversation", "bot messages ÷ conversations", "ratio",
             lambda ch: t.per_conversation(ch, n(ch, "bot"))),
        ]),
        ("Understanding and repair", [
            ("Strikes", "`fallback` + `two_strike`", "int", t.strikes),
            ("Strikes per conversation", "strikes ÷ conversations", "ratio",
             lambda ch: t.per_conversation(ch, t.strikes(ch))),
            ("Fallback rate", "strikes ÷ customer messages", "pct",
             lambda ch: _ratio(t.strikes(ch), n(ch, "user"))),
            ("Two-strike handoff offers", "`two_strike`", "int", count("turn:two_strike")),
            ("Repairs: repeat", "`repeat`", "int", count("turn:repeat")),
            ("Repairs: clarify", "`clarify`", "int", count("turn:clarify")),
            ("Frustration", "`frustration`", "int", count("turn:frustration")),
            ("Abuse", "`abuse`", "int", count("turn:abuse")),
            ("Out of scope", "`out_of_scope`", "int", count("turn:out_of_scope")),
            ("Context boosts", "`context_boost`", "int", count("sys:context_boost")),
            ("Two questions answered in one reply", "`multi_answer`", "int", count("sys:multi_answer")),
            ("Shadow matcher: messages scored", "`shadow`", "int", count("sys:shadow")),
            ("Shadow matcher: agreement", "`shadow` with `agree` true", "pct",
             lambda ch: _ratio(n(ch, "shadow_agree"), n(ch, "sys:shadow"))),
        ]),
        ("Flows and safety", [
            ("Digressions answered and resumed", "`digression:*`", "int", count("turn:digression:*")),
            ("Corrections", "`correction`", "int", count("sys:correction")),
            ("Cancel confirmations asked", "`cancel_confirm`", "int", count("turn:cancel_confirm")),
            ("Flows cancelled", "`cancel`", "int", count("turn:cancel")),
            ("Carried on after the cancel question", "`cancel_declined`", "int", count("turn:cancel_declined")),
            ("Urgent confirmations asked", "`urgent_confirm:*`", "int", count("turn:urgent_confirm:*")),
            ("Urgent flows started", "`urgent:*`", "int", count("turn:urgent:*")),
            ("Urgent confirmations declined", "`urgent_declined`", "int", count("turn:urgent_declined")),
        ]),
        ("Channels and delivery", [
            ("Delivery failures", "`send_failed` + `wa_status:failed`", "int", t.failures),
            ("Delivery failure rate", "failures ÷ bot messages (WhatsApp, Messenger)", "pct",
             t.failure_rate),
            ("Rate limited", "`rate_limited`", "int", count("sys:rate_limited")),
            ("Paused (a person has the conversation)", "`paused`", "int", count("sys:paused")),
        ]),
        ("Feedback (CSAT, sampled)", [
            ("CSAT asked", "`csat_asked`", "int", count("sys:csat_asked")),
            ("CSAT thumbs up", "`csat:up`", "int", count("turn:csat:up")),
            ("CSAT thumbs down", "`csat:down`", "int", count("turn:csat:down")),
            ("CSAT response rate", "(up + down) ÷ asked", "pct",
             lambda ch: _ratio(t.csat_answers(ch), n(ch, "sys:csat_asked"))),
            ("CSAT score (out of 5)", "thumbs-up share × 5", "ratio", t.csat_score),
        ]),
    ]


def _channel_lines(t: Traffic) -> list[str]:
    channels = t.ordered_channels()
    out = [
        "## Conversation quality by channel",
        "",
        "Source is the audit `action` each line counts. Bot actions are counted once per "
        "turn, however many bubbles the turn had. On WhatsApp and Messenger a session "
        "lasts across visits, so there “conversations” means customers active in the window.",
    ]
    for section, lines in _line_groups(t):
        rows = [
            [label, source] + [_fmt(fn(None), kind)] + [_fmt(fn(ch), kind) for ch in channels]
            for label, source, kind, fn in lines
        ]
        out += ["", f"### {section}", ""]
        out += _table(["Line", "Source", "All"] + channels, rows)
    return out


# --- §1 launch targets ---------------------------------------------------------------


def _targets(t: Traffic, offline: dict) -> list[list[str]]:
    """[area, metric, measured, by channel, target, status] per §1 target."""
    n = t.n
    active = [ch for ch in t.ordered_channels() if n(ch, "conv")]
    gates = offline.get("gates") or {}

    def per_channel(fn, kind, channels=None):
        chosen = active if channels is None else channels
        parts = [f"{ch} {_fmt(fn(ch), kind)}" for ch in chosen if fn(ch) is not None]
        return " · ".join(parts) or DASH

    def offline_row(area, metric, key, op, target, target_text):
        value = offline.get(key)
        return [area, metric, _fmt(value, "pct"), "offline", target_text, status(value, op, target)]

    rows = []
    recall = offline.get("redteam_recall")
    rows.append([
        "Safety", "Red-team fraud, theft and lost-card reports caught by the urgent scan",
        DASH if recall is None else f"{recall:.1%} ({offline['redteam_caught']}/{offline['redteam_n']})",
        "offline", "100%", status(recall, ">=", 1.0),
    ])
    hard = offline.get("redteam_hard_false")
    rows.append([
        "Safety", "Red-team everyday messages sent straight into a report, without asking",
        DASH if hard is None else f"{hard} of {offline['redteam_neg_n']}",
        "offline", "0", status(hard, "<=", 0),
    ])
    gate = gates.get("b77_urgent_recall_min")
    rows.append([
        "Safety", "BANKING77 fraud and lost-card phrasings caught (CI gate)",
        _fmt(offline.get("b77_urgent_recall"), "pct"), "offline",
        DASH if gate is None else f"≥ {gate:.1%} (gate)",
        NA if gate is None else status(offline.get("b77_urgent_recall"), ">=", gate),
    ])
    rows.append(offline_row("Safety", "Out-of-scope questions answered directly (held-out set)",
                            "oos_direct", "<=", 0.03, "≤ 3%"))
    rows.append(offline_row("Understanding", "In-scope questions answered right and directly",
                            "right_direct", ">=", 0.85, "≥ 85%"))
    rows.append(offline_row("Understanding", "In-scope questions right or one tap away",
                            "one_tap", ">=", 0.95, "≥ 95%"))
    rows.append(offline_row("Understanding", "Questions answered wrongly and confidently",
                            "wrong_direct", "<=", 0.02, "≤ 2%"))

    def strikes_per_conv(ch):
        return t.per_conversation(ch, t.strikes(ch))

    rows.append([
        "Conversation", "Strikes per conversation", _fmt(strikes_per_conv(None), "ratio"),
        per_channel(strikes_per_conv, "ratio"), "pilot baseline, then halve it", NA,
    ])
    rows.append(["Access to humans", "Handoff SLA met", DASH, DASH, "≥ 95%", f"{NA} (needs H2)"])

    score, answers = t.csat_score(None), t.csat_answers(None)
    rows.append([
        "Outcome", "CSAT (thumbs-up share × 5)",
        DASH if score is None else f"{score:.2f} ({n(None, 'turn:csat:up')} of {answers} thumbs up)",
        per_channel(t.csat_score, "ratio"), "≥ 4.2", status(score, ">=", 4.2),
    ])
    rows.append([
        "Channels", "Delivery failures (WhatsApp, Messenger)", _fmt(t.failure_rate(None), "pct"),
        per_channel(t.failure_rate, "pct", [c for c in MESSAGING if n(c, "bot")]),
        "≤ 1%", status(t.failure_rate(None), "<=", 0.01),
    ])

    def bot_per_conv(ch):
        return t.per_conversation(ch, n(ch, "bot"))

    rows.append([
        "Channels", "Bot messages per conversation", _fmt(bot_per_conv(None), "ratio"),
        per_channel(bot_per_conv, "ratio"), "≤ 4 average", status(bot_per_conv(None), "<=", 4),
    ])
    return rows


# --- Tickets, WhatsApp cost, leads ---------------------------------------------------


def _ticket_lines(tickets, channels) -> list[str]:
    kinds = sorted({"fraud", "complaint", "callback"} | {k for k, _, _ in tickets})
    by = collections.Counter((k, ch) for k, ch, _ in tickets)
    total = collections.Counter(k for k, _, _ in tickets)
    rows = [[kind, str(total[kind])] + [str(by[kind, ch]) for ch in channels] for kind in kinds]
    rows.append(["**Total**", str(len(tickets))] + [str(sum(by[k, ch] for k in kinds)) for ch in channels])
    return ["## Tickets by type and channel", "", "Source: the `tickets` table.", ""] + _table(
        ["Type", "All"] + channels, rows
    )


def _whatsapp_cost_lines(t: Traffic, days: int) -> list[str]:
    sent = t.n("whatsapp", "bot")
    allowance = config.WA_FREE_SERVICE_MESSAGES * days / DAYS_PER_MONTH
    billable = max(0, round(sent - allowance))
    templates = t.n("whatsapp", "template_sent")
    cost = (billable + templates) * config.WA_UTILITY_RATE
    conversations = t.n("whatsapp", "conv")
    rows = [
        ["WhatsApp bot messages", "role `bot` on `whatsapp`", _fmt(sent, "int")],
        [f"Free service messages for {days} days", f"{config.WA_FREE_SERVICE_MESSAGES:,} a month, "
         f"prorated [VERIFY]", _fmt(round(allowance), "int")],
        ["Billable service messages", "bot messages − free allowance", _fmt(billable, "int")],
        ["Utility templates sent (always billable)", "`template:*` sent", _fmt(templates, "int")],
        ["Rate per message", "`WA_UTILITY_RATE` [VERIFY]", _fmt(config.WA_UTILITY_RATE, "usd4")],
        ["**Estimated cost**", "(billable + templates) × rate", _fmt(cost, "usd")],
        ["Estimated cost per WhatsApp conversation", "cost ÷ WhatsApp conversations",
         _fmt(_ratio(cost, conversations), "usd4")],
    ]
    return [
        "## Estimated WhatsApp cost",
        "",
        "An estimate only. Meta bills in US dollars (not converted to ZMW here), and the free "
        "allowance is per number per calendar month, so a weekly window can only prorate it. "
        "Both the rate and the allowance are marked [VERIFY] until checked against Meta's "
        "current rate card (see docs/multi-platform-research.md §8).",
        "",
    ] + _table(["Line", "Source", "Value"], rows)


def topic_group(text: str) -> str:
    """The intent category the matcher reads in a callback topic."""
    from app.router import OUT_OF_SCOPE, matcher

    ranked = matcher.match(text or "")
    if not ranked:
        return OTHER_TOPIC
    top, score = ranked[0]
    if score < config.MEDIUM_CONFIDENCE or top == OUT_OF_SCOPE:
        return OTHER_TOPIC
    return TOPIC_GROUPS.get(matcher.get(top).get("category"), OTHER_TOPIC)


def _consent(fields: dict) -> str:
    value = fields.get("marketing_consent")
    text = "" if value is None else str(value).strip().lower()
    return {"yes": "yes", "true": "yes", "no": "no", "false": "no"}.get(text, "unknown")


def _clean_value(value) -> str | None:
    """A free-text field fit to print: "" when missing, None when it still
    looks personal (withheld)."""
    text = " ".join(str(value or "").split()).strip(" .!?")
    if not text:
        return ""
    return None if looks_personal(text) else text


def _lead_lines(tickets, channels) -> list[str]:
    callbacks = [(ch, fields) for kind, ch, fields in tickets if kind == "callback"]
    out = [
        "## Lead generation (for Marketing)",
        "",
        "Callback requests (`callback` tickets) in the window. Names and phone numbers are "
        "never shown here; they are on the tickets for the contact centre.",
        "",
    ]
    by_channel = collections.Counter(ch for ch, _ in callbacks)
    out += _table(["Channel", "Callbacks"],
                  [[ch, str(by_channel[ch])] for ch in channels] + [["**All**", str(len(callbacks))]])
    if not callbacks:
        return out + ["", "No callback requests in this window."]

    groups = collections.Counter(topic_group(fields.get("topic", "")) for _, fields in callbacks)
    out += ["", "### By topic", "",
            "The matcher's best guess at what each customer asked to discuss.", ""]
    out += _table(["Topic", "Callbacks"], [[g, str(c)] for g, c in groups.most_common()])

    typed, withheld = collections.Counter(), 0
    for _, fields in callbacks:
        text = _clean_value(fields.get("topic"))
        if text is None:
            withheld += 1
        else:
            typed[text.lower() or "(none given)"] += 1
    out += ["", "### Topics as typed (masked)", ""]
    out += _table(["Topic", "Callbacks"], [[_cell(t), str(c)] for t, c in typed.most_common(TOPICS_SHOWN)])
    if withheld:
        out.append(f"\n{withheld} withheld because they looked personal.")

    sources = collections.Counter()
    for _, fields in callbacks:
        value = _clean_value(fields.get("source"))
        sources["(withheld)" if value is None else (value or "unknown")] += 1
    out += ["", "### By campaign source", "",
            "The ticket's `source` field; “unknown” where none was recorded.", ""]
    out += _table(["Source", "Callbacks"], [[_cell(s), str(c)] for s, c in sources.most_common()])

    out += ["", "### Marketing consent", ""]
    if not any("marketing_consent" in fields for _, fields in callbacks):
        return out + ["Not recorded on any callback in this window."]
    consent = collections.Counter(_consent(fields) for _, fields in callbacks)
    out += _table(["Consent", "Callbacks"], [[k, str(consent[k])] for k in ("yes", "no", "unknown")])
    out.append(f"\nShare of callbacks with marketing consent: "
               f"{_fmt(_ratio(consent['yes'], len(callbacks)), 'pct')} (yes ÷ all callbacks).")
    return out


# --- The report ----------------------------------------------------------------------


def build_report(days: int = 7, offline: dict | None = None, run_offline: bool = True) -> str:
    """The markdown report. `offline` injects the evaluation numbers (tests);
    otherwise they are measured now unless run_offline is False."""
    audit.init_db()
    con = sqlite3.connect(audit.DB_FILE)
    since = _since(days)
    try:
        t = collect(con, since)
        tickets = load_tickets(con, since)
        unmatched, withheld = top_unmatched(con, since)
        campaigns = _campaigns(con, since)
    finally:
        con.close()
    if offline is None:
        offline = offline_metrics() if run_offline else {}

    t.channels |= {ch for _, ch, _ in tickets}
    channels = t.ordered_channels()
    now = dt.datetime.now(dt.timezone.utc)
    targets = _targets(t, offline)
    tally = collections.Counter(row[-1].split()[0] for row in targets)
    score, answers = t.csat_score(None), t.csat_answers(None)
    callbacks = sum(1 for kind, _, _ in tickets if kind == "callback")
    per_channel = " · ".join(f"{ch} {t.n(ch, 'conv'):,}" for ch in channels)

    lines = [
        f"# Chatbot weekly quality report: last {days} days",
        "",
        f"Generated {now:%d/%m/%Y %H:%M} UTC for {now - dt.timedelta(days=days):%d/%m/%Y} to "
        f"{now:%d/%m/%Y}, by `python -m admin.report`.",
        "",
        "## Summary",
        "",
        f"- {t.n(None, 'conv'):,} conversations ({per_channel}) and {callbacks:,} callback requests.",
        f"- Launch targets: {tally[PASS]} met, {tally[FAIL]} not met, {tally[NA]} without data "
        "or not yet measurable.",
        "- CSAT: " + (f"{score:.2f} out of 5 from {answers:,} answers." if answers else "no answers yet."),
        "- Draft figures: a qualified person checks them before they go into a management report.",
        "",
        "## Launch targets (excellence plan §1)",
        "",
        "Offline rows are measured now on the production matcher"
        + (f" ({offline['mode']} mode)" if offline.get("mode") else "")
        + "; the others come from this window's traffic."
        + ("" if offline else " The offline evaluation was skipped (--skip-eval)."),
        "",
    ]
    lines += _table(["Area", "Metric", "Measured", "By channel", "Launch target", "Status"], targets)
    lines += [""] + _channel_lines(t)
    lines += [""] + _ticket_lines(tickets, channels)
    lines += [""] + _whatsapp_cost_lines(t, days)
    lines += [""] + _lead_lines(tickets, channels)
    lines += campaigns
    lines += ["", "## Top unmatched utterances (feed these back into intents/*.yaml)", ""]
    if unmatched:
        lines += _table(["Utterance (masked)", "Count"], [[_cell(text), str(n)] for text, n in unmatched])
    else:
        lines.append("None in this window.")
    if withheld:
        lines.append(f"\n{withheld} withheld because they looked personal.")
    turns = sorted(
        ((name[5:], sum(v for (k, _), v in t.counts.items() if k == name))
         for name in {k for k, _ in t.counts if k.startswith("turn:")}),
        key=lambda kv: (-kv[1], kv[0]),
    )
    lines += ["", "## All bot actions (turns)", ""]
    lines += _table(["Action", "Count"], [[a, str(c)] for a, c in turns]) if turns else ["None."]
    lines.append("")
    return "\n".join(lines)


def _campaigns(con, since) -> list[str]:
    """MK3: sessions and callbacks per campaign source, marketing consent and
    opt-outs. Counts only -- names and numbers stay in Jira."""
    sessions = dict(
        con.execute(
            "SELECT substr(text, 9), COUNT(DISTINCT session_id) FROM events "
            "WHERE action='session_source' AND ts >= ? GROUP BY text",
            (since,),
        ).fetchall()
    )
    callbacks, consent = {}, {}
    for (raw,) in con.execute(
        "SELECT fields FROM tickets WHERE type='callback' AND created >= ?", (since,)
    ):
        try:
            fields = json.loads(raw or "{}")
        except ValueError:
            fields = {}
        source = fields.get("source") or "unknown"
        callbacks[source] = callbacks.get(source, 0) + 1
        if fields.get("marketing_consent") == "yes":
            consent[source] = consent.get(source, 0) + 1
    opt_outs = con.execute(
        "SELECT COUNT(*) FROM events WHERE action='marketing_opt_out' AND role='system' AND ts >= ?",
        (since,),
    ).fetchone()[0]
    lines = [
        "",
        "## Campaigns (source from data-campaign, utm_* or a wa.me ref: token)",
        "",
        f"Marketing opt-outs: {opt_outs}",
        "",
        "| Source | Sessions | Callbacks | Callbacks with marketing consent |",
        "|---|---|---|---|",
    ]
    for source in sorted(set(sessions) | set(callbacks), key=lambda s: (-callbacks.get(s, 0), s)):
        lines.append(
            f"| {source} | {sessions.get(source, 0)} | {callbacks.get(source, 0)} | {consent.get(source, 0)} |"
        )
    return lines


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Weekly chatbot quality report")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=Path, default=None,
                        help="write markdown here (default: data/report.md)")
    parser.add_argument("--stdout", action="store_true", help="print instead of writing a file")
    parser.add_argument("--skip-eval", action="store_true",
                        help="skip the offline evaluation (about 5 s); its targets show n/a")
    args = parser.parse_args(argv)
    report = build_report(args.days, run_offline=not args.skip_eval)
    if args.stdout:
        if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
            sys.stdout.reconfigure(encoding="utf-8")
        print(report)
        return
    out = args.out or config.DATA_DIR / "report.md"
    out.write_text(report, encoding="utf-8")
    print(f"written: {out}")


if __name__ == "__main__":
    main()
