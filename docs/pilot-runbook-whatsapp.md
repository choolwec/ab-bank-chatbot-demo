# WhatsApp pilot runbook (ticket W10)

> **Draft for the product owner and contact-centre lead to review**, with
> Legal and Compliance consulted. Written 24/09/2026. Dates follow
> `execution-plan.md` §12 and move if a gate isn't met.

## Summary

The WhatsApp bot goes live in two stages, each with its own go/no-go:

| Stage | When | Who can reach the bot | Gate to the next stage |
|---|---|---|---|
| 1. Staff pilot | W15–W16 (04/01/2027 – 15/01/2027) | About 30 named staff | §5 criteria on pilot data |
| 2. Limited public pilot | W17 onwards (from 18/01/2027) | Customers who scan a branch QR code or tap the website's "Continue on WhatsApp" link | §5 criteria, then M6 (`go-no-go.md`) |

There is **no mass marketing** during either stage. If anything goes badly
wrong, the PO or CC lead turns WhatsApp off in under 15 minutes (§8).

Before stage 1 starts, `go-no-go.md` M4 rows 4.1–4.12, 4.15 and 4.16 must
be signed.

## 1. Roles

| Role | Who (to confirm) | Pilot duties |
|---|---|---|
| **Product owner (PO)** | Project lead | Chairs the daily triage; makes every go/no-go call; owns the kill switch decision; sends the weekly status note |
| **Contact-centre lead (CC)** | Contact centre | Runs the handoff queue and its SLA; tags `bot-wrong`; can pull the kill switch out of hours; recruits staff testers from the CC |
| **Social-media team (SM)** | Social team | During coexistence, answers handoffs from the WhatsApp Business app on 0769651262; tags `bot-wrong`; recruits testers |
| **Developer (Dev)** | Developer | Produces the weekly report; fixes defects; runs the kill-switch commands during business hours; writes post-mortems with the PO |
| Compliance | Compliance / IT risk | Told within the hour of any Sev 1 (R1); attends the stage go/no-go |
| Content owner (CO) | Marketing / product | Rewords answers flagged in triage; every change goes through Legal before a production release |

On call follows R1: the Dev during business hours; out of hours, only the
kill switches, used by the PO or CC lead.

## 2. Stage 1: staff pilot (about 30 staff, 2 weeks)

**Who.** About 30 staff from the contact centre, social team, branches and
head office, chosen so that some are comfortable with Bemba or Nyanja and
some rarely use WhatsApp for work. The CC lead keeps the list of names
(outside git).

**What testers are told** (a short briefing in W15, Monday):

- Use your own WhatsApp to message the bank's number, as a customer would.
- **Use made-up details only.** Never send a real card, account or NRC
  number, a PIN, or a real customer's name. For phone numbers use your own
  work number or a clearly fake one (0977 000 000).
- Try everyday questions, typos, voice notes, photos, shared locations,
  "talk to a person", and a pretend fraud report. Try to break it.
- After anything odd, fill in the feedback form (§7). One form per problem.
- Fraud tests go to the real fraud team's queue. Start every pretend fraud
  report with the word **TEST** so the team can close it without action.

**Channel setup.** Coexistence (option B, see `decisions-log.md`): the bot
answers on the Cloud API; staff who handle WhatsApp today keep the Business
app. A reply from the app must pause the bot for that customer.
**Not built yet (24/09/2026):** the WhatsApp adapter does not yet act on
Meta's coexistence echo events (`smb_message_echoes` in the research,
**[VERIFY]** the name), so today the bot would keep answering while a person
replies from the app. It needs a ticket and a test before the staff pilot
(`go-no-go.md` row 4.16).

**Daily triage.** 15 minutes at 09:30 on working days (template in §6):

1. The Dev brings the overnight numbers from
   `python -m admin.report --days 1` (and the weekly `data/report.md` on
   Mondays), plus the new feedback forms and `bot-wrong` tags from Jira (and
   Chatwoot once H2 exists).
2. Each new item gets a severity (§4), an owner and a due date.
3. Anything Sev 1 is handled at once, not at the next triage.

**Weekly.** On Friday the PO attaches the weekly report to the status note.
The Dev runs `python -m admin.export_utterances --days 7` so two reviewers
can label the week's messages (N1).

## 3. Stage 2: limited public pilot (W17 onwards)

**How customers find it — only these two routes:**

- A **QR code at branches** (counter and banking-hall posters) that opens a
  chat with the official number. Marketing prints it; the Dev supplies the
  `wa.me` link.
- The **"Continue on WhatsApp"** button in the website widget: a plain
  `wa.me/260769651262` link with **no session data** in the URL. It stays off
  until stage 2 is approved (see `decisions-log.md`).

No SMS blasts, social posts, emails or press. If a campaign source is
tracked, it is a short code in the pre-filled first message or link (for
example the branch name), never a customer identifier.

**Triage.** Same daily 15 minutes. From week 2 of stage 2, the PO may move
it to three times a week if there has been no Sev 1 or Sev 2 for 7 days.

**Capacity.** The CC lead watches handoff volume daily. If handoffs exceed
what the team can answer within the SLA, the PO can remove the website link
(one setting) while the QR codes stay.

## 4. Severity mapping (same levels as R1)

The severity table in `docs/runbook-incidents.md` (R1) is the source of
truth. For the pilot:

| Severity | Pilot examples | First response |
|---|---|---|
| **Sev 1** | A fraud or lost-card report not routed to the fraud flow; any unmasked card, account, NRC or PIN in logs, Jira or reports; a wrong fee, rate or contact number quoted; a message sent to the wrong customer; the bot replying while a person is handling the chat, repeatedly | Kill switch (§8) within 15 minutes; PO and Compliance told; fix; post-mortem within 2 working days. **Stage clock restarts** (§5). |
| **Sev 2** | WhatsApp down or not replying; webhook failures; send failures above target; the Meta quality rating drops; a handoff not picked up within the SLA | Fix within 1 working day |
| **Sev 3** | A wrong-but-safe answer; a clumsy wording; a "did you mean" that missed; a missing phrasing | Next content release; phrasing goes to the N1 labelling queue |

A tester's "severity" on the feedback form is only a suggestion; triage
decides.

## 5. Go/no-go per stage

A stage passes only when all three hold on that stage's data:

1. **§1 targets** from `excellence-plan.md`, measured by the weekly report:
   - fraud, theft and lost-card reports reach the fraud flow: 100% (red-team
     suite green and no missed report found in triage);
   - no everyday message sent into fraud or complaint without asking;
   - out-of-scope answered directly ≤ 3%; right ≥ 85%; wrong ≤ 2%;
   - ≤ 4 bot messages per conversation on average;
   - delivery failures ≤ 1%;
   - CSAT ≥ 4.2 (if enough responses; staff CSAT is indicative only).
2. **No Sev 1 in the last 7 days.**
3. **Handoff SLA ≥ 95%**: handoffs answered within the promised time (CC
   lead's count from the queue until H2 measures it).

The PO records the decision in the milestone table in `go-no-go.md` (row
4.13 for stage 1). A **no-go** means another week of the same stage, then
re-check. Two no-gos in a row go to the sponsor.

If a target can't be measured yet (for example CSAT with very few
responses), the PO writes "not enough data" and the reason; that is not a
pass.

## 6. Daily triage template

Copy into the pilot's shared notes each day. No customer names, numbers or
full transcripts; use ticket references (FRD-…, CMP-…, CBK-…, HND-…) and audit
session ids only.

```
WhatsApp pilot triage — DD/MM/YYYY — stage 1 / stage 2 — day N
Present: PO, CC, SM, Dev (+ Compliance if a Sev 1)

1. Numbers since last triage (python -m admin.report --days 1)
   Conversations: __   Handoffs: __   Handoffs within SLA: __ / __
   Fraud reports: __   Complaints: __   Callbacks: __
   Fallbacks / two-strike handoffs: __ / __   Delivery failures: __
   Anything off target? ______________________

2. New items (feedback forms, bot-wrong tags, alerts)
   | # | Source | What happened (no personal data) | Ref / session id | Severity | Owner | Due |
   |---|--------|----------------------------------|------------------|----------|-------|-----|

3. Open items from earlier days: status of each

4. Sev 1 in the last 7 days? yes / no   (date of the last one: __/__/____)

5. Decisions / changes for today's release (content changes need Legal)

6. Kill switch used since last triage? yes / no — why, by whom, restored when
```

## 7. Staff feedback form

One form per problem (a Microsoft Form or a shared sheet; the CC lead owns
it). The form must not collect customer data.

| Field | Type | Notes |
|---|---|---|
| Date and time of the message | Date/time | Lets the Dev find it in the audit log |
| Your team | Choice: CC / social / branch / head office / other | No name needed |
| What did you send? | Short text | Paste your message. **Made-up details only.** |
| What did the bot do? | Short text | Or a screenshot with personal details blurred |
| What should it have done? | Short text | |
| Language | Choice: English / Bemba-English / Nyanja-English / other | Feeds N8 |
| How bad is it? | Choice: Dangerous (fraud missed, wrong fee, private data) / Wrong but harmless / Awkward wording / Suggestion | A suggestion only; triage decides |
| Did you ask for a person? Did someone reply in time? | Choice: yes-in time / yes-late / no reply / didn't ask | Feeds the handoff SLA |
| Anything else | Long text | |

## 8. Rollback: the kill switch

Turning WhatsApp off never means silence: the bot sends one static, approved
reply (at most hourly per customer) pointing to a person, so customers are
never left without an answer.

**Business hours (Dev):**

1. On the production VM, edit `flags.json` in the app folder and set
   `"WHATSAPP_ENABLED": false`. Flags are re-read on every message: **no
   restart**. (Setting the `WHATSAPP_ENABLED` environment variable instead
   also works but needs a service restart and wins over the file.)
   **Check before the pilot:** the production env file must **not** set
   `WHATSAPP_ENABLED` (or `FREE_TEXT_ENABLED`, `EMBEDDINGS_ENABLED`,
   `URGENT_MODEL_ENABLED`). An environment variable wins over `flags.json`
   (`app/config.py::flag`), so if one is set, editing `flags.json` silently
   does nothing. The rehearsal (`go-no-go.md` row 4.11) proves this.
2. Send a test message from a staff phone and check you get the static
   reply.
3. Post in the pilot Teams chat: time, who, why.

**Out of hours (PO or CC lead):** use the steps in
`docs/runbook-incidents.md` (R1), which give the exact commands for the
people who hold VM access.

**Softer options**, for problems that don't need the whole channel off:

| Problem | Switch | Effect |
|---|---|---|
| Free-text answers going wrong | `"FREE_TEXT_ENABLED": false` | Menu-only mode on every channel; fraud, complaints and handoff still work |
| The hybrid matcher misbehaving | `"EMBEDDINGS_ENABLED": false` | Back to the character matcher |
| The model-based urgent check misfiring | `"URGENT_MODEL_ENABLED": false` | Rule-based urgent scan only |
| Too many public-pilot handoffs | Remove the website link (widget setting) | QR codes still work |

**Restoring:** set the flag back to `true`, test from a staff phone, and
note it in the triage log. After a Sev 1, the PO decides when to restore,
after the fix is deployed.

**Full rollback of a bad release:** redeploy the previous release tag using
`docs/runbook-production.md` (P7).

## 9. After the pilot

At the end of each stage the PO writes a half-page summary for the status
note: numbers against §1, the Sev 1/2 list with post-mortem links, what
changed, and the go/no-go decision. The labelled messages feed the golden
set (N1) and the code-mixed set (N8).
