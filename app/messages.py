"""Built-in texts (ticket C1), loaded from knowledge/system_messages.yaml.

msg("fallback") returns the wording; msg("fraud.finish", ref=ref) fills the
code-supplied placeholders. CONTACTS placeholders ({contact_phone} ...) are
left in place for router._render(), which fills them on every reply, so a
contact change never needs a message edit.

verify() runs at import: every msg("...") key referenced anywhere in app/
must exist, or start-up fails with a KeyError -- a typo'd key is caught
before the first customer sees a blank reply.
"""

import re

import yaml

from . import config

MESSAGES_FILE = config.KNOWLEDGE_DIR / "system_messages.yaml"
APP_DIR = config.BASE_DIR / "app"
STATUSES = ("draft", "legal_review", "approved")
# msg("key" ...) and msg('key' ...) with a literal first argument.
REFERENCE_RE = re.compile(r"""\bmsg\(\s*["']([a-z][a-z0-9_.]*)["']""")
BUTTON_RE = re.compile(r"""\bbutton\(\s*["']([a-z][a-z0-9_]*)["']""")
VARIANT_RE = re.compile(r"""\bvariant\(\s*["']([a-z][a-z0-9_.]*)["']""")


class _Keep(dict):
    """Unknown {placeholders} survive formatting (for router._render)."""

    def __missing__(self, key):
        return "{" + key + "}"


def load() -> dict[str, dict]:
    data = yaml.safe_load(MESSAGES_FILE.read_text(encoding="utf-8")) or {}
    messages = data.get("messages") or {}
    for key, entry in messages.items():
        if not isinstance(entry, dict) or not str(entry.get("text", "")).strip():
            raise ValueError(f"system message {key!r} has no text")
        variants = entry.get("variants")
        if variants is not None and (not isinstance(variants, list) or not all(str(v).strip() for v in variants)):
            raise ValueError(f"system message {key!r} has empty or malformed variants")
        if entry.get("status", "draft") not in STATUSES:
            raise ValueError(f"system message {key!r} has unknown status {entry.get('status')!r}")
    return messages


MESSAGES = load()


def msg(key: str, **fmt) -> str:
    text = str(MESSAGES[key]["text"]).strip()
    if fmt:
        text = text.format_map(_Keep({k: str(v) for k, v in fmt.items()}))
    return text


def has(key: str) -> bool:
    return key in MESSAGES


def button(key: str, payload: str) -> dict:
    """A button whose label is msg("button.<key>") (C11)."""
    return {"label": msg(f"button.{key}"), "payload": payload}


def variant(key: str, n: int) -> str:
    """The n-th of a message's `variants:` (wrapping), for wording that may
    rotate without touching facts -- e.g. "Got it." / "Thanks." (C11).
    Deterministic: the caller picks n (e.g. the turn number)."""
    entry = MESSAGES[key]
    options = entry.get("variants") or [entry["text"]]
    return str(options[n % len(options)]).strip()


def referenced_keys() -> set[str]:
    keys = set()
    for path in APP_DIR.rglob("*.py"):
        if path.name == "messages.py":  # its docstring shows example calls
            continue
        source = path.read_text(encoding="utf-8")
        keys.update(REFERENCE_RE.findall(source))
        keys.update("button." + k for k in BUTTON_RE.findall(source))
        keys.update(VARIANT_RE.findall(source))
    return keys


def verify() -> None:
    missing = sorted(referenced_keys() - set(MESSAGES))
    if missing:
        raise KeyError(f"system messages missing from {MESSAGES_FILE.name}: {missing}")


verify()
