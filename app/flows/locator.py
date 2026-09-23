"""Branch & agent locator (§3.1A), backed by knowledge/branches.json.

Remembers the city as a context slot. Two misses end the flow with a human
offer instead of trapping the user (mirrors the two-strike rule).
"""

import json

from .. import config
from ..messages import msg
from .base import CANCEL_BUTTON, HUMAN_BUTTON, MENU_BUTTON


AGENT_WORDS = frozenset({
    "agent", "agents", "an agent", "etumba agent", "etumba agents", "an etumba agent",
})


def _load() -> dict:
    return json.loads(config.BRANCHES_FILE.read_text(encoding="utf-8"))


def find_branches(needle: str) -> list[dict]:
    """Branches whose city or name contains `needle` (case-insensitive)."""
    needle = (needle or "").lower().strip()
    if not needle:
        return []
    return [
        b for b in _load()["branches"]
        if needle in b["city"].lower() or needle in b["name"].lower()
    ]


def branch_lines(branches: list[dict]) -> str:
    return "\n".join(
        msg(
            "locator.branch_line",
            name=b["name"], address=b["address"], city=b["city"],
            phone=b["phone"], hours=b["hours"],
        )
        for b in branches
    )


class LocatorFlow:
    name = "locator"

    @property
    def topic_label(self) -> str:
        return msg("locator.topic_label")

    def message_keys(self):
        return ["locator.topic_label"]

    def start(self, session, kind=None, trigger=None):
        session.active_flow = self.name
        session.flow_state = {"mode": kind, "misses": 0}
        if kind == "agent":
            session.active_flow = None
            session.flow_state = {}
            return self._agents(), True
        if kind == "branch":
            return [self._city_prompt(msg("locator.city_intro"))], False
        return [self._mode_prompt()], False

    def _mode_prompt(self):
        return {
            "text": msg("locator.mode"),
            "buttons": [
                {"label": "A branch", "payload": "loc_branch"},
                {"label": "An eTumba agent", "payload": "loc_agent"},
                CANCEL_BUTTON,
            ],
        }

    def resume(self, session):
        if session.flow_state.get("mode") is None:
            return [self._mode_prompt()]
        return [self._city_prompt("")]

    def handle(self, session, text, payload=None):
        state = session.flow_state
        if state.get("mode") is None:
            if payload == "loc_agent" or "agent" in (text or "").lower():
                session.flow_state = {}
                return self._agents(), True
            state["mode"] = "branch"
            if payload == "loc_branch" or not (text or "").strip():
                return [self._city_prompt("")], False
        city = (payload or text or "").strip()
        if not city:
            return [self._city_prompt("")], False
        if " ".join(city.lower().split()) in AGENT_WORDS:
            # "agent" typed at the town question means an eTumba agent.
            session.flow_state = {}
            return self._agents(), True
        return self._branch_lookup(session, city)

    def _city_prompt(self, prefix):
        cities = sorted({b["city"] for b in _load()["branches"]})
        text = (prefix + " " if prefix else "") + msg("locator.city")
        buttons = [{"label": c, "payload": c} for c in cities] + [CANCEL_BUTTON]
        return {"text": text, "buttons": buttons}

    def _agents(self):
        networks = ", ".join(n["name"] for n in _load()["agent_networks"])
        return [
            {
                "text": msg("locator.agents", networks=networks),
                "buttons": [
                    {"label": "Find a branch", "payload": "branch_locator"},
                    {"label": "About eTumba", "payload": "etumba_what_is"},
                    MENU_BUTTON,
                ],
            }
        ]

    def found_reply(self, session, matches):
        session.slots["city"] = matches[0]["city"]
        return {
            "text": msg("locator.found", lines=branch_lines(matches)),
            "buttons": [
                {"label": "eTumba agents", "payload": "agent_locator"},
                {"label": "Opening hours", "payload": "opening_hours"},
                MENU_BUTTON,
            ],
        }

    def _branch_lookup(self, session, city):
        matches = find_branches(city)
        if matches:
            return [self.found_reply(session, matches)], True
        state = session.flow_state
        state["misses"] = state.get("misses", 0) + 1
        cities = sorted({b["city"] for b in _load()["branches"]})
        if state["misses"] >= 2:
            text = msg("locator.not_found_final", cities=", ".join(cities))
            return [{"text": text, "buttons": [HUMAN_BUTTON, MENU_BUTTON]}], True
        buttons = [{"label": c, "payload": c} for c in cities] + [
            HUMAN_BUTTON,
            CANCEL_BUTTON,
        ]
        return [{"text": msg("locator.not_found", city=city), "buttons": buttons}], False
