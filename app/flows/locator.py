"""Branch & agent locator (§3.1A), backed by knowledge/branches.json.

Remembers the city as a context slot. Two misses end the flow with a human
offer instead of trapping the user (mirrors the two-strike rule).
"""

import json

from .. import config
from .base import CANCEL_BUTTON, HUMAN_BUTTON, MENU_BUTTON


def _load() -> dict:
    return json.loads(config.BRANCHES_FILE.read_text(encoding="utf-8"))


class LocatorFlow:
    name = "locator"

    def start(self, session, kind=None):
        session.active_flow = self.name
        session.flow_state = {"mode": kind, "misses": 0}
        if kind == "agent":
            session.active_flow = None
            session.flow_state = {}
            return self._agents(), True
        if kind == "branch":
            return [self._city_prompt("Happy to help you find a branch.")], False
        return [
            {
                "text": "Are you looking for a branch, or an eTumba cash-in/"
                "cash-out agent?",
                "buttons": [
                    {"label": "A branch", "payload": "loc_branch"},
                    {"label": "An eTumba agent", "payload": "loc_agent"},
                    CANCEL_BUTTON,
                ],
            }
        ], False

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
        return self._branch_lookup(session, city)

    def _city_prompt(self, prefix):
        cities = sorted({b["city"] for b in _load()["branches"]})
        text = (prefix + " " if prefix else "") + "Which town or city are you in?"
        buttons = [{"label": c, "payload": c} for c in cities] + [CANCEL_BUTTON]
        return {"text": text, "buttons": buttons}

    def _agents(self):
        networks = ", ".join(n["name"] for n in _load()["agent_networks"])
        text = (
            "You can put money into or take money out of your eTumba wallet at "
            f"any AB Bank branch, and at these agent networks countrywide: "
            f"{networks}. Look for their signage at shops and kiosks near you. "
            "[CONFIRM: guidance for finding a specific nearby agent.]"
        )
        return [
            {
                "text": text,
                "buttons": [
                    {"label": "Find a branch", "payload": "branch_locator"},
                    {"label": "About eTumba", "payload": "etumba_what_is"},
                    MENU_BUTTON,
                ],
            }
        ]

    def _branch_lookup(self, session, city):
        branches = _load()["branches"]
        needle = city.lower().strip()
        matches = [
            b
            for b in branches
            if needle and (needle in b["city"].lower() or needle in b["name"].lower())
        ]
        if matches:
            session.slots["city"] = matches[0]["city"]
            lines = [
                f"- {b['name']} — {b['address']}, {b['city']}. "
                f"Phone: {b['phone']}. Hours: {b['hours']}"
                for b in matches
            ]
            text = "Here's what I found:\n" + "\n".join(lines)
            return [
                {
                    "text": text,
                    "buttons": [
                        {"label": "eTumba agents", "payload": "agent_locator"},
                        {"label": "Opening hours", "payload": "opening_hours"},
                        MENU_BUTTON,
                    ],
                }
            ], True
        state = session.flow_state
        state["misses"] = state.get("misses", 0) + 1
        cities = sorted({b["city"] for b in branches})
        if state["misses"] >= 2:
            text = (
                "I couldn't find a listed branch there. We currently list "
                f"branches in: {', '.join(cities)}. Our team can help you find "
                "the nearest service point."
            )
            return [{"text": text, "buttons": [HUMAN_BUTTON, MENU_BUTTON]}], True
        text = (
            f"I don't have a branch listed for '{city}' yet. Try one of these "
            "towns, or ask for a person:"
        )
        buttons = [{"label": c, "payload": c} for c in cities] + [
            HUMAN_BUTTON,
            CANCEL_BUTTON,
        ]
        return [{"text": text, "buttons": buttons}], False
