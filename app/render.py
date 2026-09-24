"""Per-channel rendering (ticket P3, multi-platform-research §7.3).

Pure functions: router replies [{text, buttons}] -> each platform's native
message bodies. The renderer may RE-SHAPE buttons (reply buttons, a list,
quick replies) but never removes the way to a person: if the reply offered
"Talk to a person", the rendered message does too.

Limits (Appendix A of the research; Meta values marked [VERIFY] there):
  WhatsApp  text 4096 · interactive body 1024 · reply buttons <=3, title <=20
            list: button text <=20, <=10 rows, row title <=24, description <=72
            ids <=256
  Messenger text 2000 · quick replies <=13, title <=20, payload <=1000
Titles use `short_label` (K1) when the full label is too long; a label that is
too long AND has no short_label is truncated here, and
tests/test_render_limits.py fails the build so content gets fixed.
"""

from .messages import msg

WA_TEXT_MAX = 4096
WA_BODY_MAX = 1024
WA_BUTTONS_MAX = 3
WA_BUTTON_TITLE_MAX = 20
WA_LIST_ROWS_MAX = 10
WA_ROW_TITLE_MAX = 24
WA_ROW_DESC_MAX = 72
WA_LIST_BUTTON_MAX = 20
WA_ID_MAX = 256

MS_TEXT_MAX = 2000
MS_QUICK_REPLIES_MAX = 13
MS_TITLE_MAX = 20
MS_PAYLOAD_MAX = 1000

HUMAN_PAYLOAD = "human_handoff"
MORE_PAYLOAD = "more_options"


def title_for(button: dict, limit: int) -> str:
    """The label that fits: the full label, else short_label, else cut."""
    label = button["label"]
    if len(label) <= limit:
        return label
    short = button.get("short_label") or ""
    if short and len(short) <= limit:
        return short
    return label[: limit - 1].rstrip() + "…"


def _fit_options(buttons: list[dict], max_items: int) -> list[dict]:
    """At most max_items; overflow becomes a "More…" option. The human
    option is kept even if it would otherwise fall off the end."""
    if len(buttons) <= max_items:
        return list(buttons)
    head = list(buttons[: max_items - 1])
    human = next((b for b in buttons if b["payload"] == HUMAN_PAYLOAD), None)
    if human and human not in head:
        head[-1] = human
    return head + [{"label": msg("button.more"), "payload": MORE_PAYLOAD}]


def _split(text: str, limit: int) -> list[str]:
    """Split long text on paragraph, then line, then word boundaries."""
    chunks, rest = [], text
    while len(rest) > limit:
        cut = max(rest.rfind("\n\n", 0, limit), rest.rfind("\n", 0, limit), rest.rfind(" ", 0, limit))
        if cut <= 0:
            cut = limit
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    chunks.append(rest)
    return [c for c in chunks if c]


# --- WhatsApp Cloud API ------------------------------------------------------

def whatsapp(reply: dict) -> list[dict]:
    """One router reply -> WhatsApp message bodies (without "to")."""
    text = reply.get("text") or ""
    buttons = reply.get("buttons") or []
    out: list[dict] = []
    if not buttons:
        return [{"type": "text", "text": {"body": c, "preview_url": False}} for c in _split(text, WA_TEXT_MAX)]
    body = text
    if len(text) > WA_BODY_MAX:
        # Costs an extra message: avoid in content (every answer is <= 755 today).
        out += [{"type": "text", "text": {"body": c, "preview_url": False}} for c in _split(text, WA_TEXT_MAX)]
        body = msg("choose_below")
    if len(buttons) <= WA_BUTTONS_MAX:
        out.append({
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": [
                    {"type": "reply", "reply": {"id": b["payload"][:WA_ID_MAX], "title": title_for(b, WA_BUTTON_TITLE_MAX)}}
                    for b in buttons
                ]},
            },
        })
        return out
    rows = []
    for b in _fit_options(buttons, WA_LIST_ROWS_MAX):
        row = {"id": b["payload"][:WA_ID_MAX], "title": title_for(b, WA_ROW_TITLE_MAX)}
        if row["title"] != b["label"]:
            row["description"] = b["label"][:WA_ROW_DESC_MAX]
        rows.append(row)
    out.append({
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {"button": msg("button.choose_an_option")[:WA_LIST_BUTTON_MAX],
                       "sections": [{"title": msg("button.options")[:24], "rows": rows}]},
        },
    })
    return out


def whatsapp_all(replies: list[dict]) -> list[dict]:
    return [m for r in replies for m in whatsapp(r)]


# --- Messenger Send API --------------------------------------------------------

def messenger(reply: dict) -> list[dict]:
    """One router reply -> Messenger `message` objects (without recipient).
    Plain text + quick replies, never a button template: templates cap text
    at 640 chars and one answer is 755."""
    text = reply.get("text") or ""
    buttons = reply.get("buttons") or []
    chunks = _split(text, MS_TEXT_MAX) or [""]
    out = [{"text": c} for c in chunks]
    if buttons:
        out[-1]["quick_replies"] = [
            {"content_type": "text", "title": title_for(b, MS_TITLE_MAX), "payload": b["payload"][:MS_PAYLOAD_MAX]}
            for b in _fit_options(buttons, MS_QUICK_REPLIES_MAX)
        ]
    return out


# --- Website ---------------------------------------------------------------------

def web(reply: dict) -> list[dict]:
    """The widget renders router replies as they are."""
    return [reply]


RENDERERS = {"web": web, "whatsapp": whatsapp, "messenger": messenger}


def render(channel: str, replies: list[dict]) -> list[dict]:
    out = []
    for reply in replies:
        out += RENDERERS[channel](reply)
    return out
