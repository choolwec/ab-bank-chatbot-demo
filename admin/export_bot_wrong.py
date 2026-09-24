"""Add what agents tagged "bot got this wrong" to the labelling queue (ticket H4).

Usage:  python -m admin.export_bot_wrong [--days 7] [--out data/utterances.csv]

Agents add the label `bot-wrong` to a Chatwoot conversation (H2), or to the
Jira issue of a ticket. This script, run weekly:

  1. pulls Chatwoot conversations labelled bot-wrong with activity in the
     last --days (skipped if the desk isn't configured), and Jira issues with
     that label updated in the same period, by JQL (skipped if Jira isn't
     configured; the mock log has no labels);
  2. keeps only CUSTOMER turns: the "[user] ..." lines of the transcript
     (the desk's handoff note, the Jira description), which is where the bot
     went wrong, plus the messages the customer sent to the agent;
  3. drops button taps and anything that still looks personal, with the same
     second PII check as admin/export_utterances.py;
  4. appends what's new to data/utterances.csv with source=bot-wrong, the
     current matcher's prediction, and empty labels. Rows already in the CSV
     (same text, any case) are skipped.

That feeds the normal N1 flow: two reviewers fill label_a / label_b, then
`python -m admin.import_labels data/utterances.csv`. Only counts are
printed, never message text.

Weekly cron, AFTER export_utterances (which rewrites the CSV), next to the
H6 report:
    15 6 * * 1  cd /opt/abz-chatbot && .venv/bin/python -m admin.export_bot_wrong --days 7
"""

import argparse
import csv
import re
import time
from pathlib import Path

import httpx

from admin.export_utterances import FIELDS, looks_personal
from app import config
from app.desk import chatwoot

LABEL = "bot-wrong"
SOURCE = "bot-wrong"
USER_LINE_RE = re.compile(r"^\[user\] (.+)$", re.MULTILINE)
JIRA_MAX_PAGES = 20


def _is_incoming(message: dict) -> bool:
    # the messages listing uses 0 for incoming, webhooks use "incoming" [VERIFY]
    return message.get("message_type") in (0, "incoming") and not message.get("private")


def chatwoot_turns(client, since: float) -> tuple[list[str], int]:
    """Customer turns from labelled conversations -> (texts, conversations)."""
    if not client.configured():
        return [], 0
    conversations = client.labelled_conversations(LABEL, since)
    texts = []
    for conv in conversations:
        for m in client.conversation_messages(chatwoot.conversation_id(conv)):
            content = m.get("content") or ""
            if m.get("private"):
                texts += USER_LINE_RE.findall(content)  # the handoff transcript note
            elif _is_incoming(m):
                texts.append(content)
    return texts, len(conversations)


def jira_turns(days: int, transport=None) -> tuple[list[str], int]:
    """Customer turns from Jira issues labelled bot-wrong -> (texts, issues)."""
    if not config.jira_configured():
        return [], 0
    jql = (f'project = "{config.JIRA_PROJECT_KEY}" AND labels = "{LABEL}" '
           f"AND updated >= -{int(days)}d ORDER BY updated DESC")
    # Jira Cloud's enhanced search, paged by nextPageToken [VERIFY]: the older
    # /rest/api/2/search is being retired. v2 keeps the description plain text.
    url = f"{config.JIRA_BASE_URL.rstrip('/')}/rest/api/2/search/jql"
    texts, issues, token = [], 0, None
    with httpx.Client(transport=transport, timeout=15) as client:
        for _ in range(JIRA_MAX_PAGES):
            params = {"jql": jql, "fields": "description", "maxResults": 50}
            if token:
                params["nextPageToken"] = token
            response = client.get(url, params=params, auth=(config.JIRA_EMAIL, config.JIRA_API_TOKEN))
            response.raise_for_status()
            data = response.json()
            for issue in data.get("issues", []):
                issues += 1
                description = (issue.get("fields") or {}).get("description") or ""
                if isinstance(description, str):
                    texts += USER_LINE_RE.findall(description)
            token = data.get("nextPageToken")
            if not token or data.get("isLast", False):
                break
    return texts, issues


def keep(texts: list[str], existing: set[str]) -> tuple[list[str], dict]:
    """Customer turns worth labelling: no button taps, nothing personal, new."""
    kept, stats = [], {"personal": 0, "duplicate": 0}
    seen = set(existing)
    for text in texts:
        text = " ".join((text or "").split())
        if not text or text.startswith("["):
            continue
        if looks_personal(text):
            stats["personal"] += 1
            continue
        if text.lower() in seen:
            stats["duplicate"] += 1
            continue
        seen.add(text.lower())
        kept.append(text)
    return kept, stats


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def append(path: Path, texts: list[str]) -> int:
    """Append new rows, adding the `source` column to an older CSV."""
    from app.matcher import Matcher

    matcher = Matcher()
    rows = _read(path)
    for text in texts:
        ranked = matcher.match(text)
        top, score = ranked[0] if ranked else ("", 0.0)
        rows.append({"text": text, "predicted_intent": top, "score": f"{score:.3f}", "action": "",
                     "label_a": "", "label_b": "", "source": SOURCE})
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)
    return len(texts)


def _failure(exc: Exception) -> str:
    """Why a source failed, without echoing any response body."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return str(exc) if isinstance(exc, chatwoot.ChatwootError) else type(exc).__name__


def export(days: int, out: Path, client=None, jira_transport=None) -> dict:
    """One source failing never loses the other's rows; errors are reported."""
    client = client or chatwoot.client
    since = time.time() - days * 86400
    errors = {}
    desk_texts, conversations = [], 0
    try:
        desk_texts, conversations = chatwoot_turns(client, since)
    except (chatwoot.ChatwootError, httpx.HTTPError, ValueError) as exc:
        errors["chatwoot"] = _failure(exc)
    jira_texts, issues = [], 0
    try:
        jira_texts, issues = jira_turns(days, transport=jira_transport)
    except (httpx.HTTPError, ValueError) as exc:
        errors["jira"] = _failure(exc)
    existing = {" ".join((r.get("text") or "").split()).lower() for r in _read(out)}
    texts, stats = keep(desk_texts + jira_texts, existing)
    added = append(out, texts) if texts else 0
    return {"conversations": conversations, "issues": issues, "added": added, "errors": errors, **stats}


def main() -> None:
    parser = argparse.ArgumentParser(description='Append "bot-wrong" customer turns to the labelling CSV')
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=Path, default=config.DATA_DIR / "utterances.csv")
    args = parser.parse_args()
    result = export(args.days, args.out)
    print(f"bot-wrong: {result['conversations']} desk conversations, {result['issues']} Jira issues; "
          f"added {result['added']} to {args.out} "
          f"(dropped {result['personal']} personal, {result['duplicate']} already there)")
    for source, why in result["errors"].items():
        print(f"  FAILED {source}: {why}")
    if result["errors"]:
        raise SystemExit(1)  # cron mails the output


if __name__ == "__main__":
    main()
