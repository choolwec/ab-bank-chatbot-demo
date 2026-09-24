"""The channel interface (ticket P2, multi-platform-research §7.2).

Every channel -- website, WhatsApp, Messenger -- produces `InboundMessage`s
and hands them to `process()`, which calls the UNCHANGED router pipeline
(guards -> flows -> matcher). The CLAUDE.md invariants therefore hold on every
channel by construction: masking happens inside router.handle(), the
button guarantee is enforced there, and flows never close their own tickets.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class InboundMessage:
    channel: str                  # "web" | "whatsapp" | "messenger"
    user_key: str                 # web session id, WhatsApp BSUID/wa_id, Messenger PSID
    text: str | None = None
    payload: str | None = None    # a tapped button / list row / quick reply / postback
    location: tuple[float, float] | None = None  # (lat, lng) from a shared location
    media_type: str | None = None  # image | document | audio | video | sticker | ...
    msg_id: str | None = None      # platform message id, for de-duplication
    ts: float | None = None        # platform timestamp (seconds), for staleness
    # A phone number the platform tells us (WhatsApp). Used ONLY to offer a
    # prefill the customer confirms; never logged raw.
    phone_hint: str | None = None

    @property
    def session_key(self) -> str:
        return f"{self.channel}:{self.user_key}"


class Channel(Protocol):
    name: str

    def parse(self, raw: dict) -> list[InboundMessage]:
        """Platform webhook body -> zero or more inbound messages."""

    def send(self, user_key: str, replies: list[dict]) -> None:
        """Render `replies` ([{text, buttons}]) natively and deliver them."""

    def mark_read(self, message: InboundMessage) -> None:
        """Acknowledge receipt (read receipt / typing indicator), if supported."""
