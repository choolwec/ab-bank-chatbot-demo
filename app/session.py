"""Per-session memory (§3.1D): context slots, strike counter, 30-min timeout.

In-memory store — fine for a single small VM at <100 users/month. Transcripts
held here are ALREADY MASKED (guards run first) and capped in length.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field

from . import config

TRANSCRIPT_MAX_TURNS = 200


@dataclass
class Session:
    id: str
    created: float
    last_active: float
    strikes: int = 0
    active_flow: str | None = None
    flow_state: dict = field(default_factory=dict)
    slots: dict = field(default_factory=dict)       # topic, city, last_intent…
    transcript: list = field(default_factory=list)  # masked turns only
    greeted: bool = False
    # C3: what the last bot reply asked for -- {"options": [(label, payload)],
    # "yes": payload, "no": payload}. Rebuilt after every reply.
    expecting: dict = field(default_factory=dict)

    def add(self, role: str, text: str) -> None:
        self.transcript.append({"role": role, "text": text, "ts": time.time()})
        if len(self.transcript) > TRANSCRIPT_MAX_TURNS:
            del self.transcript[: len(self.transcript) - TRANSCRIPT_MAX_TURNS]


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str | None = None) -> tuple[Session, bool]:
        now = time.time()
        timeout = config.SESSION_TIMEOUT_MINUTES * 60
        with self._lock:
            for sid, sess in list(self._sessions.items()):
                if now - sess.last_active > timeout:
                    del self._sessions[sid]
            if session_id and session_id in self._sessions:
                sess = self._sessions[session_id]
                sess.last_active = now
                return sess, False
            new_id = uuid.uuid4().hex
            sess = Session(id=new_id, created=now, last_active=now)
            self._sessions[new_id] = sess
            return sess, True


store = SessionStore()
