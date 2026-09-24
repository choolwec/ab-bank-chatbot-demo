# Decisions log

> **Draft for the product owner to approve or reverse, item by item.** The
> PO asked for everything buildable to be built this week, assuming
> approval; these are the decisions taken on **24/09/2026** to make that
> possible. Anything the PO doesn't approve is removed before launch. Legal
> and Compliance are consulted where a row says so.

**How to use it.** For each row, the PO changes **Status** to `Approved`,
`Reversed` or `Changed: <what>`, with initials and the date (DD/MM/YYYY).
"Reversible how" says what undoing it costs. Later decisions are added as
new rows, never by editing an approved one.

## Decisions taken on 24/09/2026

| # | Decision | Rationale | Reversible how | Status |
|---|---|---|---|---|
| D1 | **Go/no-go checklists** for each milestone: M3 website, M4 WhatsApp (staff and public stages), M5 Messenger, M6 full launch, in `docs/go-no-go.md`, signed in the commit the release tag points to | R2 in the execution plan; one table per gate keeps the launch call on evidence. Signing in the tagged commit ties the signed checklist to the exact code deployed | Edit the checklist rows; the signing method can move to a PR approval if the owner returns to branches | Proposed |
| D2 | **Alerts (R1) go to a Teams group chat and open a Jira ticket** | Teams is where the PO, CC lead and Dev already talk, so alerts are seen quickly; a Jira ticket gives every incident an owner and a record for post-mortems, in the contact centre's existing queue | The destinations are configuration (`ALERT_WEBHOOK_URL` and the R1 Jira settings in the env file); changing them needs no code change | Proposed |
| D3 | **Hosting: ask the bank's IT to host internally first**; if IT can't, a Tier III data centre in Lusaka (Paratus, Infratel or MTN quotes) is the fallback. Never outside Zambia for real data | DPA s.70 localisation (Legal to confirm); BoZ cyber guidelines favour IT-owned hosting (L4); the request is in `docs/hosting-requirements-it.md`. The external route is ready if IT declines | Switch to the fallback at any time before W05; the app is the same either way | Proposed |
| D4 | **Agent desk: Chatwoot Community edition, self-hosted** in Zambia for **WhatsApp** handoff. **Messenger keeps the Page Inbox.** **Web keeps callbacks** for now | Community edition is open source (MIT) with no licence cost **[VERIFY]**; self-hosting keeps data in Zambia. The social team already works in the Page Inbox, and handover is built (M4). Callbacks work on the web today; live chat on the web can join Chatwoot later | Per channel: `HANDOFF_MODE_<CHANNEL>` in the env file switches between callback and inbox; without `CHATWOOT_URL` WhatsApp falls back to callbacks | Proposed |
| D5 | **WhatsApp number: coexistence (option B) on 0769651262 for the pilot, then full migration (option A)** once Chatwoot is live | Keeps the number already printed everywhere; staff keep the Business app and their chat history during the pilot; low risk. Migration later brings the free blue badge and one inbox. Moving from B to A later must be confirmed with Meta **[VERIFY]** | Before migration: stop the bot's number registration and staff carry on in the app. After migration, going back is hard (history lost) | Proposed |
| D6 | **Marketing consent question in the callback flow**, on by default (the question is asked; the answer is never assumed). **Opt-out commands** ("stop" and similar) withdraw consent at any time. **No bulk lead export**: Marketing works from callback tickets carrying a Jira label for consenting customers | Marketing wants leads; the ECT Act 2021 needs opt-in and a working opt-out, and the DPA's purpose limitation means a callback number can't be reused for marketing without consent (Legal to confirm, `legal-compliance-pack.md` §3). A label keeps data in one controlled system instead of spreadsheets | The question can be switched off by configuration if the build provides a flag, otherwise by a small content and flow change; wording is in YAML (`status: draft`) for Legal to change; the label can be dropped in Jira | Proposed |
| D7 | **Campaign source attribution**: links and QR codes carry a short campaign code (for example a branch or campaign name), recorded with the conversation | Lets Marketing see which campaign or branch brings conversations, without identifying anyone. The code is a campaign, never a person | Stop adding codes to links; old codes are harmless | Proposed |
| D8 | **"Continue on WhatsApp" link on the website stays off until WhatsApp is live** (public pilot stage, M4) | The number mustn't be promoted before the bot, templates and handoff are ready; W10 names the link as one of only two public-pilot routes | One setting turns it on at the public-pilot go decision | Proposed |
| D9 | **CSAT sampled at 20%** of resolved conversations, **never after a fraud report** | Every WhatsApp message costs money from 01/10/2026; 20% gives enough responses. Asking "how did we do?" after a fraud report reads badly (H5 plan) | `CSAT_SAMPLE_RATE` in config (0 turns it off) | Proposed |
| D10 | **Staging runs shadow mode (`SHADOW_MATCHER=true`) and fetches the embedding model** during its build | Two shadow reviews on real-looking traffic are needed before switching the hybrid matcher; without the model, staging silently runs character mode only (`remaining-work-plan.md` §4) | Remove the fetch from `render.yaml`; set the flag false | Proposed |
| D11 | **`EMBEDDINGS_ENABLED` stays off** in production until the shadow results are in; the matcher build stream makes a recommendation | Hybrid mode is better on in-scope questions but still has known issues (negation, some out-of-scope answers). Switching needs ≥ 80% shadow wins and no worse out of scope | Flip the flag in `flags.json`: no deploy, instantly reversible | Proposed |
| D12 | **K2 (resolving every `[CONFIRM`) waits for the PO's bank information**; nothing is guessed | The facts (emergency line, branch data, hours, tariff URL, complaint timelines) must come from bank owners; inventing them would be unsafe | Not applicable: each placeholder is replaced when the fact arrives | Proposed |

## Decisions added by the build streams

> Filled in by the integration step with the decisions each build stream
> took this week.

| # | Decision | Rationale | Reversible how | Status |
|---|---|---|---|---|
| — | *(placeholder: to be filled by the integration step)* | | | |
