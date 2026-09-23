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


def referenced_keys() -> set[str]:
    keys = set()
    for path in APP_DIR.rglob("*.py"):
        if path.name == "messages.py":  # its docstring shows example calls
            continue
        keys.update(REFERENCE_RE.findall(path.read_text(encoding="utf-8")))
    return keys


def verify() -> None:
    missing = sorted(referenced_keys() - set(MESSAGES))
    if missing:
        raise KeyError(f"system messages missing from {MESSAGES_FILE.name}: {missing}")


verify()
