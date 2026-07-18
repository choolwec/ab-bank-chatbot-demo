"""Deterministic priority flows (§3.1C). State lives on the session, not here."""

from .complaint import ComplaintFlow
from .fraud import FraudFlow
from .lead import LeadFlow
from .locator import LocatorFlow

FLOWS = {f.name: f for f in (FraudFlow(), ComplaintFlow(), LeadFlow(), LocatorFlow())}
