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


def free_text_enabled() -> bool:
    return flag("FREE_TEXT_ENABLED", True)


def widget_enabled() -> bool:
    return flag("WIDGET_ENABLED", True)
