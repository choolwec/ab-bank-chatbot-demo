"""Deterministic priority flows (§3.1C). State lives on the session, not here."""

from ..messages import has
from .complaint import ComplaintFlow
from .fraud import FraudFlow
from .lead import LeadFlow
from .locator import LocatorFlow

FLOWS = {f.name: f for f in (FraudFlow(), ComplaintFlow(), LeadFlow(), LocatorFlow())}


def verify_messages() -> None:
    """Flows look some keys up by convention ("fraud.step.when"), which the
    grep in messages.verify() can't see -- check those here, at import."""
    missing = sorted(
        key for flow in FLOWS.values() for key in flow.message_keys() if not has(key)
    )
    if missing:
        raise KeyError(f"system messages missing for flows: {missing}")


verify_messages()
