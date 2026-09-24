"""Messenger Page profile, as code (ticket M3).

Usage:
    python -m admin.messenger_profile            # print the payload (dry run)
    python -m admin.messenger_profile --apply    # POST it to /me/messenger_profile

Sets the Get Started button, the greeting (automated-assistant disclosure +
scope), a persistent menu mirroring the bot's main menu -- "Talk to a person"
is always in it, because quick replies disappear once used -- and 3-4 ice
breakers. All wording comes from knowledge/system_messages.yaml
(messenger.*), so it goes through the same legal review. Needs MS_PAGE_TOKEN
for --apply. Limits [VERIFY against Meta docs]: greeting <= 160 chars,
persistent-menu titles <= 30, ice breakers <= 4.
"""

import argparse
import json
import sys

GREETING_MAX = 160
MENU_TITLE_MAX = 30
ICE_BREAKERS_MAX = 4


def build_profile() -> dict:
    from app.messages import msg
    from app.router import MENU_BUTTONS

    menu = [{"type": "postback", "title": b["label"][:MENU_TITLE_MAX], "payload": b["payload"]} for b in MENU_BUTTONS]
    if not any(item["payload"] == "human_handoff" for item in menu):
        menu.append({"type": "postback", "title": msg("button.talk_to_a_person"), "payload": "human_handoff"})
    return {
        "get_started": {"payload": "start"},
        "greeting": [{"locale": "default", "text": msg("messenger.greeting")[:GREETING_MAX]}],
        "persistent_menu": [{"locale": "default", "composer_input_disabled": False, "call_to_actions": menu}],
        "ice_breakers": [
            {"call_to_actions": [
                {"question": msg(f"messenger.ice_breaker.{i}"), "payload": payload}
                for i, payload in enumerate(["etumba_what_is", "branch_locator", "fraud_scam", "human_handoff"], 1)
            ][:ICE_BREAKERS_MAX], "locale": "default"}
        ],
    }


def apply(profile: dict) -> int:
    import httpx

    from app import config

    token = config.ms_settings()["page_token"]
    if not token:
        print("MS_PAGE_TOKEN is not set: nothing sent.", file=sys.stderr)
        return 2
    url = f"{config.GRAPH_BASE_URL}/{config.WA_GRAPH_VERSION}/me/messenger_profile"
    response = httpx.post(url, params={"access_token": token}, json=profile, timeout=15)
    print(response.status_code, response.text)
    return 0 if response.status_code < 300 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Messenger Page profile (Get Started, greeting, menu, ice breakers)")
    parser.add_argument("--apply", action="store_true", help="send it to Meta (needs MS_PAGE_TOKEN)")
    args = parser.parse_args()
    profile = build_profile()
    if args.apply:
        sys.exit(apply(profile))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(profile, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
