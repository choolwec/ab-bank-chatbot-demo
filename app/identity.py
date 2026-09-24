"""Hashed customer identities for the audit trail (ticket P6).

A WhatsApp user key is a phone number or BSUID; a Messenger one is a PSID.
Neither may ever be logged raw: the audit log stores

    user_hash = HMAC-SHA256(USER_KEY_SECRET, "channel:user_key")[:32]

which is stable (the same customer always gets the same hash, so reports can
count conversations per person) but useless to anyone without the secret.

USER_KEY_SECRET comes from the environment in production. If it isn't set,
a random secret is generated once into data/ (never git) so hashes stay
stable across restarts on a dev machine or staging.
"""

import hashlib
import hmac
import os
import secrets
import threading

from . import config

_SECRET_FILE = "user_key_secret"
_lock = threading.Lock()
_cached: bytes | None = None


def _secret() -> bytes:
    global _cached
    env = os.environ.get("USER_KEY_SECRET")
    if env:
        return env.encode()
    with _lock:
        if _cached is None:
            path = config.DATA_DIR / _SECRET_FILE
            if not path.exists():
                path.write_text(secrets.token_hex(32), encoding="utf-8")
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
            _cached = path.read_text(encoding="utf-8").strip().encode()
        return _cached


def user_hash(key: str) -> str:
    return hmac.new(_secret(), key.encode(), hashlib.sha256).hexdigest()[:32]


# --- Sealed reply addresses (W2, H1) ------------------------------------------
# To answer a WhatsApp or Messenger customer we need their raw platform id,
# including later (an agent's reply, a case_update template). It is stored
# only ENCRYPTED ("sealed"), never in the audit log. REPLY_KEY is a Fernet key
# from the environment in production; otherwise one is generated into data/.
#
# P7: REPLY_KEY may hold several keys, comma-separated. The FIRST seals; every
# one unseals (MultiFernet), so the key can be rotated without losing a stored
# value: put the new key first, restart, run `python -m admin.rotate_reply_key`
# to re-seal what is stored, then drop the old key (runbook-production.md).
_REPLY_KEY_FILE = "reply_key"
_file_keys: str | None = None
_ciphers = None  # (key source, MultiFernet, primary Fernet)


def _key_source() -> str:
    global _file_keys
    env = os.environ.get("REPLY_KEY")
    if env:
        return env
    from cryptography.fernet import Fernet

    with _lock:
        if _file_keys is None:
            path = config.DATA_DIR / _REPLY_KEY_FILE
            if not path.exists():
                path.write_bytes(Fernet.generate_key())
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
            _file_keys = path.read_text(encoding="utf-8")
        return _file_keys


def reply_keys(source: str | None = None) -> list[bytes]:
    """The configured keys, primary first (commas or newlines separate them)."""
    source = _key_source() if source is None else source
    return [k.strip().encode() for k in source.replace("\n", ",").split(",") if k.strip()]


def _cipher_pair():
    global _ciphers
    from cryptography.fernet import Fernet, MultiFernet

    source = _key_source()
    cached = _ciphers
    if cached is None or cached[0] != source:
        keys = reply_keys(source)
        if not keys:
            raise ValueError("REPLY_KEY is set but holds no key")
        fernets = [Fernet(k) for k in keys]
        cached = (source, MultiFernet(fernets), fernets[0])
        _ciphers = cached
    return cached[1], cached[2]


def _cipher():
    return _cipher_pair()[0]


def seal(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()


def unseal(token: str) -> str:
    return _cipher().decrypt(token.encode()).decode()


def reseal(token: str) -> str:
    """The same value, sealed again with the primary key (rotation). Raises
    cryptography.fernet.InvalidToken if no configured key opens it."""
    return _cipher().rotate(token.encode()).decode()


def sealed_with_primary(token: str) -> bool:
    from cryptography.fernet import InvalidToken

    try:
        _cipher_pair()[1].decrypt(token.encode())
    except (InvalidToken, ValueError, TypeError):
        return False
    return True
