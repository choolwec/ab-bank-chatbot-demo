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

# --- Session (§3.1D) ---
SESSION_TIMEOUT_MINUTES = 30

# --- Input hygiene (§3.3) ---
MAX_MESSAGE_CHARS = 500
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20"))

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

# --- Contact details, rendered into answers as {placeholders}. ---
# Every [CONFIRM …] value must be replaced (env var or here) before launch.
CONTACTS = {
    "bank_name": "AB Bank Zambia",
    "emergency_phone": os.environ.get(
        "ABZ_EMERGENCY_PHONE", "[CONFIRM: 24hr emergency / card-block line]"
    ),
    "contact_phone": os.environ.get(
        "ABZ_CONTACT_PHONE", "[CONFIRM: customer care line]"
    ),
    "contact_email": os.environ.get(
        "ABZ_CONTACT_EMAIL", "[CONFIRM: customer care email]"
    ),
    "website_url": os.environ.get(
        "ABZ_WEBSITE_URL", "[CONFIRM: official website URL]"
    ),
    "tariff_url": os.environ.get(
        "ABZ_TARIFF_URL", "[CONFIRM: link to current tariff guide]"
    ),
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
