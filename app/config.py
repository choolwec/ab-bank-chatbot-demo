"""Central configuration: thresholds, feature flags, kill switches, contacts.

Kill switches (build plan §3.3) can be flipped WITHOUT a redeploy: set the
environment variable, or edit flags.json in the repo root — flags.json is
re-read on every check. Env var wins over file, file wins over default.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
INTENTS_DIR = KNOWLEDGE_DIR / "intents"
BRANCHES_FILE = KNOWLEDGE_DIR / "branches.json"
DATA_DIR = BASE_DIR / "data"
FLAGS_FILE = BASE_DIR / "flags.json"

DATA_DIR.mkdir(exist_ok=True)

# --- Free-text matching thresholds (§3.1B) ---
HIGH_CONFIDENCE = 0.70    # answer directly
MEDIUM_CONFIDENCE = 0.45  # "Did you mean…?" candidate buttons
SUGGESTION_COUNT = 3

# --- Session (§3.1D, ticket P1) ---
# Idle this long: greet again, but keep any half-finished flow.
IDLE_REGREET_MINUTES = int(os.environ.get("IDLE_REGREET_MINUTES", "30"))
SESSION_TIMEOUT_MINUTES = IDLE_REGREET_MINUTES  # pre-P1 name, kept for scripts
# A flow left this long is dropped; fraud reports and complaints get longer.
FLOW_EXPIRY_HOURS = int(os.environ.get("FLOW_EXPIRY_HOURS", "24"))
FLOW_EXPIRY_HOURS_URGENT = int(os.environ.get("FLOW_EXPIRY_HOURS_URGENT", "72"))

# --- Input hygiene (§3.3) ---
MAX_MESSAGE_CHARS = 500
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20"))
# Per customer on the Meta webhooks (P4): they all arrive from Meta's IPs.
USER_RATE_LIMIT_PER_MINUTE = int(os.environ.get("USER_RATE_LIMIT_PER_MINUTE", "20"))


def proxy_hops() -> int:
    """Number of reverse proxies in front of this app (nginx/IIS/load
    balancer). 0 = none, rate-limit on the socket peer address. Set to 1 (or
    however many proxies IT runs) in production so the limiter sees real
    client IPs from X-Forwarded-For instead of one shared proxy IP."""
    try:
        return int(os.environ.get("PROXY_HOPS", "0"))
    except ValueError:
        return 0

# --- Retention, in days — numbers TO BE CONFIRMED BY LEGAL (§3.3 / §7) ---
TRANSCRIPT_RETENTION_DAYS = int(os.environ.get("TRANSCRIPT_RETENTION_DAYS", "90"))
# 0 = never auto-purge; complaint/fraud tickets follow the complaints unit's policy
TICKET_RETENTION_DAYS = int(os.environ.get("TICKET_RETENTION_DAYS", "0"))

# --- CORS: lock to the bank's domain in production (§3.3) ---
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        # dev defaults; in production set ALLOWED_ORIGINS=https://<bank domain>
        "http://127.0.0.1:8000,http://localhost:8000",
    ).split(",")
    if o.strip()
]

# --- Jira handoff (contact-center integration) ---
# Off by default: no real project/token exists yet. When turned on without
# credentials, jira_export.py falls back to a MOCK issue log instead of
# failing, so a demo can show "what would land in Jira" with zero setup.
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEY = os.environ.get("JIRA_PROJECT_KEY", "")
# Issue-key prefix used only in mock mode (e.g. "CC-7"); harmless placeholder.
JIRA_MOCK_PROJECT_KEY = os.environ.get("JIRA_MOCK_PROJECT_KEY", "CC")


def jira_enabled() -> bool:
    return flag("JIRA_ENABLED", False)


def jira_configured() -> bool:
    return bool(JIRA_BASE_URL and JIRA_EMAIL and JIRA_API_TOKEN and JIRA_PROJECT_KEY)


# --- Admin routes (every /admin/*, ticket P8) ---
# HTTP Basic auth. OFF by default: with ADMIN_USER/ADMIN_PASSWORD unset every
# /admin/* route returns 404, so a fresh deploy never exposes customer names,
# phone numbers or transcripts. Read per request so a rotation takes effect
# without a restart.


def admin_credentials() -> tuple[str, str] | None:
    user = os.environ.get("ADMIN_USER", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    return (user, password) if user and password else None


# --- Contact details, rendered into answers as {placeholders}. ---
# Sourced from the Branch Staff FAQ Document + Social Media Response
# Template (12.08.2025) — see knowledge/faq/fees-and-contact.md for the
# per-fact citations. Remaining [CONFIRM …] values must be replaced (env
# var or here) before launch.
CONTACTS = {
    "bank_name": "AB Bank Zambia",
    # No 24hr line was found in either source document or in web research —
    # the Contact Centre's own confirmed hours don't cover evenings/Sundays/
    # holidays, so this is a real gap, not just an unconfirmed number.
    "emergency_phone": os.environ.get(
        "ABZ_EMERGENCY_PHONE",
        "[CONFIRM: no 24hr emergency/card-block line found — confirm "
        "whether one exists, or whether 888 is the only route even "
        "outside Contact Centre hours]",
    ),
    "contact_phone": os.environ.get(
        "ABZ_CONTACT_PHONE", "888 (not toll-free)"
    ),
    "contact_email": os.environ.get(
        "ABZ_CONTACT_EMAIL", "contact@abbank.co.zm"
    ),
    "website_url": os.environ.get(
        "ABZ_WEBSITE_URL", "https://www.abbank.co.zm"
    ),
    # Best candidate found via web search (AB Bank's own site blocked
    # automated fetches — see knowledge/faq/company.md) — NOT independently
    # content-verified. Confirm with a normal browser before launch.
    "tariff_url": os.environ.get(
        "ABZ_TARIFF_URL", "https://www.abbank.co.zm/quick-links/"
    ),
    "whatsapp_number": "0769651262",
    "ussd_code": "*888#",
}


# --- Local embedding model (N3) ---------------------------------------------
# sentence-transformers/all-MiniLM-L6-v2 (Apache-2.0), downloaded once by
# `python -m admin.fetch_model` from its official source at this pinned
# revision. The files are NOT in git; each must match its sha256 or the app
# refuses to load them and keeps the character matcher.
EMBED_MODEL_DIR = Path(os.environ.get("EMBED_MODEL_DIR", str(BASE_DIR / "models" / "all-MiniLM-L6-v2")))
EMBED_MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
EMBED_MODEL_SHA256 = {
    "tokenizer.json": "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
    "onnx/model.onnx": "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452",  # = HF LFS sha256
}


# Embedding-similarity thresholds for the decision in hybrid mode. Set by
# calibration (N5, `python -m admin.calibrate`), never tuned on the test split.
EMB_HIGH = float(os.environ.get("EMB_HIGH", "0.715"))  # N5: seed 7, OOS <= 3% on calibration
EMB_MEDIUM = float(os.environ.get("EMB_MEDIUM", "0.41"))  # N5: OOS suggestions <= 45%, so gibberish falls back


# N7: similarity to an exemplar fraud report that triggers the soft-urgent
# question when no rule fired. Set by `python -m admin.calibrate_urgent`.
EMB_URGENT = float(os.environ.get("EMB_URGENT", "0.73"))  # false confirmations <= 2% when tuned


def embeddings_enabled() -> bool:
    """Kill switch (N3). Off, or model missing/unverified -> exactly the
    pre-N3 character matcher."""
    return flag("EMBEDDINGS_ENABLED", False)


# --- Contact-centre hours (H3), Lusaka time --------------------------------
# weekday (0 = Monday) -> (open, close). From the opening_hours answer:
# Monday-Friday 08:00-17:00, "Saturday morning only". The Saturday times are
# [CONFIRM: exact Saturday Contact Centre hours] -- Operations (O1).
CONTACT_CENTRE_HOURS = {
    0: ("08:00", "17:00"), 1: ("08:00", "17:00"), 2: ("08:00", "17:00"),
    3: ("08:00", "17:00"), 4: ("08:00", "17:00"), 5: ("08:00", "12:00"),
}
# ISO dates the Contact Centre is closed. [CONFIRM: the bank's holiday list
# for each year] -- set PUBLIC_HOLIDAYS=2026-10-18,2026-10-24,... or extend here.
_DEFAULT_HOLIDAYS = "2026-10-18,2026-10-24,2026-12-25,2027-01-01"


def public_holidays() -> set[str]:
    raw = os.environ.get("PUBLIC_HOLIDAYS", _DEFAULT_HOLIDAYS)
    return {d.strip() for d in raw.split(",") if d.strip()}


# --- Sampled one-tap CSAT (H5) ----------------------------------------------
# Share of customers asked "how did I do?" after a resolved conversation. The
# sample is deterministic per customer (from user_hash). On WhatsApp the
# question is merged into the resolving reply, so it costs no extra message,
# but the tap's reply does: Ops can lower this, or set 0 to stop asking, with
# no restart (env var > flags.json > default, like the kill switches).
CSAT_SAMPLE_RATE_DEFAULT = 0.2


def csat_sample_rate() -> float:
    raw = os.environ.get("CSAT_SAMPLE_RATE")
    if raw is None:
        raw = _flags_from_file().get("CSAT_SAMPLE_RATE", CSAT_SAMPLE_RATE_DEFAULT)
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return CSAT_SAMPLE_RATE_DEFAULT
    return min(max(rate, 0.0), 1.0)


def _flags_from_file() -> dict:
    try:
        return json.loads(FLAGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def flag(name: str, default: bool = True) -> bool:
    env = os.environ.get(name)
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    value = _flags_from_file().get(name)
    if isinstance(value, bool):
        return value
    return default


# --- Messaging channels (W2-W8, M2-M5) ----------------------------------------
# Secrets come from the environment ONLY (never flags.json or git). With them
# unset, the adapters run in MOCK mode: sends are written to
# data/<channel>_outbox_mock.jsonl (with a hashed recipient) instead of Meta.
WA_GRAPH_VERSION = os.environ.get("WA_GRAPH_VERSION", "v23.0")  # [VERIFY] current version
GRAPH_BASE_URL = os.environ.get("GRAPH_BASE_URL", "https://graph.facebook.com")
# A message older than this (Meta retries after an outage) is answered with an
# apology and the menu, never used to resume a flow (W8).
STALE_MESSAGE_MINUTES = int(os.environ.get("STALE_MESSAGE_MINUTES", "10"))
# WhatsApp and Messenger allow free-form replies for 24 h after the
# customer's last message; after that only an approved template (W7/W8).
CUSTOMER_WINDOW_HOURS = 24


def wa_settings() -> dict:
    return {
        "token": os.environ.get("WA_ACCESS_TOKEN", ""),
        "phone_number_id": os.environ.get("WA_PHONE_NUMBER_ID", ""),
        "app_secret": os.environ.get("WA_APP_SECRET", ""),
        "verify_token": os.environ.get("WA_VERIFY_TOKEN", ""),
    }


def ms_settings() -> dict:
    return {
        "page_token": os.environ.get("MS_PAGE_TOKEN", ""),
        "page_id": os.environ.get("MS_PAGE_ID", ""),
        "app_secret": os.environ.get("MS_APP_SECRET", ""),
        "verify_token": os.environ.get("MS_VERIFY_TOKEN", ""),
        "app_id": os.environ.get("MS_APP_ID", ""),
    }


def handoff_mode(channel: str) -> str:
    """How "Talk to a person" works per channel: "callback" (the lead flow:
    a person calls within a working day) or "inbox" (a person replies in the
    same conversation: the Messenger Page Inbox, or the agent desk, H2).
    Override with HANDOFF_MODE_<CHANNEL>."""
    default = {"messenger": "inbox"}.get(channel, "callback")
    if channel == "whatsapp" and os.environ.get("CHATWOOT_URL"):
        default = "inbox"
    return os.environ.get(f"HANDOFF_MODE_{channel.upper()}", default).strip().lower()


def channel_enabled(channel: str) -> bool:
    """Per-channel kill switches (P4). Off never means silence on a Meta
    channel: the customer gets one static reply pointing to a person."""
    if channel == "whatsapp":
        return flag("WHATSAPP_ENABLED", True)
    if channel == "messenger":
        return flag("MESSENGER_ENABLED", True)
    return widget_enabled()


def free_text_enabled() -> bool:
    return flag("FREE_TEXT_ENABLED", True)


def widget_enabled() -> bool:
    return flag("WIDGET_ENABLED", True)
