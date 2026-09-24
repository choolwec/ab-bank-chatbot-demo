"""Channel adapters (ticket P2): each turns a platform's traffic into
InboundMessage objects for the one channel-agnostic pipeline in base.py,
and sends the replies back in the platform's native shape (render.py)."""
