"""Per-conversation memory (§3.1D, ticket P1): context slots, strikes, flows.

Sessions are keyed by `channel:user_key` -- the web uses its random session
id as the user key; WhatsApp and Messenger use the platform's user id. The
`Session.id` handed to the audit log is always an opaque random id, never a
phone number or platform id.

Two timeouts, deliberately separate:
  IDLE_REGREET_MINUTES  after this long idle the customer is greeted again,
                        but any half-finished flow is KEPT (resume() re-asks it)
  FLOW_EXPIRY_HOURS     a flow left this long is dropped (longer for fraud and
                        complaint reports, which are never lost lightly)

`SqliteSessionStore` (production) survives restarts; `SessionStore` keeps
everything in memory (tests, scripts). Both serialise access per key: use
`with store.session(...) as (session, created):` so two requests for the same
customer can't interleave, and the session is saved on exit. Transcripts held
here are ALREADY MASKED (guards run first) and capped in length.

Still exactly one process: the per-key locks live in process memory (see
CLAUDE.md). Scaling out means moving the locks and store to Redis.
"""

import contextlib
import dataclasses
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field

from . import config
from .identity import user_hash

TRANSCRIPT_MAX_TURNS = 200


@dataclass
class Session:
    id: str
    created: float
    last_active: float
    channel: str = "web"
    strikes: int = 0
    active_flow: str | None = None
    flow_state: dict = field(default_factory=dict)
    slots: dict = field(default_factory=dict)       # topic, city, last_intent…
    transcript: list = field(default_factory=list)  # masked turns only
    greeted: bool = False
    # C3: what the last bot reply asked for -- {"options": [(label, payload)],
    # "yes": payload, "no": payload}. Rebuilt after every reply.
    expecting: dict = field(default_factory=dict)
    # C4: the last bot replies (masked, rendered) for "repeat", and the
    # intent they answered, for "what do you mean?".
    last_replies: list = field(default_factory=list)
    last_answer_intent: str | None = None
    # When the current flow last moved, for FLOW_EXPIRY_HOURS.
    flow_touched: float = 0.0
    # Set on load when the customer comes back after IDLE_REGREET_MINUTES.
    returning: bool = False
    # Messaging channels (W8, M4): the 24-h window and human takeover.
    last_inbound_at: float = 0.0
    bot_paused_until: float = 0.0
    # P6: HMAC of channel:user_key -- the only customer identity the audit
    # log ever sees.
    user_hash: str = ""

    def add(self, role: str, text: str) -> None:
        self.transcript.append({"role": role, "text": text, "ts": time.time()})
        if len(self.transcript) > TRANSCRIPT_MAX_TURNS:
            del self.transcript[: len(self.transcript) - TRANSCRIPT_MAX_TURNS]

    def to_json(self) -> str:
        data = dataclasses.asdict(self)
        data.pop("returning", None)  # per-load, never persisted
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "Session":
        data = json.loads(raw)
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def flow_expiry_seconds(flow: str | None) -> float:
    hours = config.FLOW_EXPIRY_HOURS_URGENT if flow in ("fraud", "complaint") else config.FLOW_EXPIRY_HOURS
    return hours * 3600


def _refresh(session: Session, now: float) -> None:
    """Apply the idle and flow-expiry rules to a session just loaded."""
    idle = now - session.last_active
    session.returning = idle > config.IDLE_REGREET_MINUTES * 60
    if session.active_flow:
        touched = session.flow_touched or session.last_active
        if now - touched > flow_expiry_seconds(session.active_flow):
            session.active_flow = None
            session.flow_state = {}
    session.last_active = now


def web_key(session_id: str) -> str:
    return f"web:{session_id}"


class _BaseStore:
    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            if len(self._locks) > 10_000:  # drop locks nobody holds
                for k in [k for k, lk in self._locks.items() if not lk.locked()]:
                    del self._locks[k]
            return self._locks.setdefault(key, threading.Lock())

    # --- storage primitives, per backend ---
    def _load(self, key: str) -> Session | None:
        raise NotImplementedError

    def _save(self, key: str, session: Session) -> None:
        raise NotImplementedError

    # --- public API ---
    def _open(self, key: str | None, channel: str) -> tuple[str, Session, bool]:
        now = time.time()
        session = self._load(key) if key else None
        if session is not None:
            _refresh(session, now)
            if not session.user_hash:  # sessions saved before P6
                session.user_hash = user_hash(key)
            return key, session, False
        session = Session(id=uuid.uuid4().hex, created=now, last_active=now, channel=channel)
        if key is None:  # web: the session id is the user key
            key = web_key(session.id)
        session.user_hash = user_hash(key)
        return key, session, True

    @contextlib.contextmanager
    def session(self, key: str | None = None, channel: str = "web"):
        """Load (or create) the session for `key`, hold its lock, save on exit."""
        if key is None:
            key_, session, created = self._open(None, channel)
            lock = self._lock_for(key_)
        else:
            lock = self._lock_for(key)
        with lock:
            if key is not None:
                key_, session, created = self._open(key, channel)
            try:
                yield session, created
            finally:
                if session.active_flow and session.flow_state:
                    session.flow_touched = time.time()
                self._save(key_, session)

    def web_session(self, session_id: str | None):
        """The widget's session: a known id resumes, anything else is new."""
        return self.session(web_key(session_id) if session_id else None, "web")

    def get_or_create(self, session_id: str | None = None) -> tuple[Session, bool]:
        """Unlocked convenience for scripts and tests: load or create, save now."""
        with self.web_session(session_id) as (session, created):
            return session, created

    def save(self, session: Session, key: str | None = None) -> None:
        self._save(key or web_key(session.id), session)

    def purge_expired(self) -> int:
        return 0


class SessionStore(_BaseStore):
    """In memory: tests, scripts, and a single short-lived process."""

    def __init__(self) -> None:
        super().__init__()
        self._sessions: dict[str, Session] = {}

    def _load(self, key):
        return self._sessions.get(key)

    def _save(self, key, session):
        self._sessions[key] = session

    def purge_expired(self) -> int:
        cutoff = time.time() - config.TRANSCRIPT_RETENTION_DAYS * 86400
        stale = [k for k, s in self._sessions.items() if s.last_active < cutoff]
        for k in stale:
            del self._sessions[k]
        return len(stale)


class SqliteSessionStore(_BaseStore):
    """Durable (P1): survives restarts; one row per `channel:user_key`."""

    def __init__(self, path=None) -> None:
        super().__init__()
        self.path = path or config.DATA_DIR / "sessions.db"
        self._db_lock = threading.Lock()  # SQLite writes are serialised
        with self._connect() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    key TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    created REAL NOT NULL,
                    last_active REAL NOT NULL,
                    state TEXT NOT NULL
                )"""
            )
            con.execute("CREATE INDEX IF NOT EXISTS sessions_last_active ON sessions(last_active)")

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def _load(self, key):
        with self._db_lock, self._connect() as con:
            row = con.execute("SELECT state FROM sessions WHERE key = ?", (key,)).fetchone()
        return Session.from_json(row[0]) if row else None

    def _save(self, key, session):
        with self._db_lock, self._connect() as con:
            con.execute(
                "INSERT INTO sessions (key, channel, created, last_active, state)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET last_active = excluded.last_active,"
                " state = excluded.state",
                (key, session.channel, session.created, session.last_active, session.to_json()),
            )

    def purge_expired(self) -> int:
        """Same schedule as the audit log (TRANSCRIPT_RETENTION_DAYS)."""
        cutoff = time.time() - config.TRANSCRIPT_RETENTION_DAYS * 86400
        with self._db_lock, self._connect() as con:
            return con.execute("DELETE FROM sessions WHERE last_active < ?", (cutoff,)).rowcount

    def count(self) -> int:
        with self._db_lock, self._connect() as con:
            return con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]


def make_store():
    """SESSION_STORE=memory keeps today's in-memory behaviour; default sqlite."""
    import os

    if os.environ.get("SESSION_STORE", "sqlite").strip().lower() == "memory":
        return SessionStore()
    return SqliteSessionStore()


store = make_store()
