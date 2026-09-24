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
_REPLY_KEY_FILE = "reply_key"
_fernet = None


def _cipher():
    global _fernet
    from cryptography.fernet import Fernet

    env = os.environ.get("REPLY_KEY")
    if env:
        return Fernet(env.encode())
    with _lock:
        if _fernet is None:
            path = config.DATA_DIR / _REPLY_KEY_FILE
            if not path.exists():
                path.write_bytes(Fernet.generate_key())
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
            _fernet = Fernet(path.read_bytes().strip())
        return _fernet


def seal(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()


def unseal(token: str) -> str:
    return _cipher().decrypt(token.encode()).decode()
