# Build summary, 02/10/2026

> **Draft.** Prepared from the code for the product owner. All customer
> wording stays draft until Legal signs it off (`docs/intent-review.md`,
> regenerated today). Decisions D17-D30 in `docs/decisions-log.md` record
> what was decided and how to undo each one.

## Summary

The bot was reworked for the demo and for lead generation. It follows the
team's flow document, answers in short messages, holds a natural
conversation, and turns interest in a product into a callback ticket
without asking the customer what they were interested in. The full test
suite passes (1,670 tests), and the held-out quality gates improved in both
matcher modes. The demo site (Render) runs this version with the draft
notes hidden.

## What changed

| Area | What the customer sees | Where |
|---|---|---|
| Flow document | Menu: Accounts / Loans / Invest / Digital Banking / Branches & agents / Complaints / Talk to an Agent, with the document's wording in full | `router.MENU_BUTTONS`, `wording: flow_doc` |
| Short answers | A short answer first, with **More details** for the rest | `answer_short` in the intents |
| Leads | **Yes, contact me** on every product; the callback form asks name, phone, time and (optionally) marketing consent, then sends. The ticket's topic is the product, plus every product viewed | `app/flows/lead.py` |
| Callback form | Takes everything at once ("my name is Mary Banda, call me on 0977… in the afternoon"), reads it back, asks only what is missing; no "Here's what I'll send" step | `LeadFlow` |
| Conversation | Natural replies to hi / how are you / bye / thanks / "no"; "tell me more", "go back", "the first one"; recovery from "no, I meant savings" and "that's not what I asked"; no pressure after "let me think" | `app/router.py`, `knowledge/system_messages.yaml` |
| Branches mid-form | "Where is the Kitwe branch?" during any form is answered, then the same question is asked again | `router._locator_digression` |
| Product owner's rules | No cards; KYC changes and closures at a branch or by callback; transfers to other banks by eTumba or Online Banking (above K20,000 Online Banking); deposits at a branch or from mobile money; any motorbike / tricycle / tractor → Trader Mobility Loan | `router._KEYWORD_INTENTS` and new intents |
| Loans | Micro and SME loan details from abbank.co.zm behind **More details**; Agro and Trader Mobility terms awaiting the loans team | `knowledge/intents/loans.yaml`, `knowledge/faq/loans.md` |
| Safety | A caller asking for a PIN or OTP is now a fraud report; failed or missing transactions offer a complaint | `app/guards.py` |
| Clear chat | A **Clear** button (and "start over") gives a fresh conversation; inside a fraud report it asks first | `widget/`, `router` |
| Demo switch | `HIDE_DRAFT_NOTES` hides `[CONFIRM …]` notes for demos | `flags.json` / env, on in `render.yaml` |

## Quality

About 500 realistic messages and conversations (Zambian English, text-speak,
typos, greetings around requests) were tested and fixed in five rounds; they
are now a permanent test (`tests/test_natural_conversation.py`). Details and
before/after counts: `docs/conversation-probe-2026-10-02.md`.

| Held-out gate | Character matcher (live) | Hybrid matcher (off) |
|---|---|---|
| Right answers given directly | 0.670 → 0.681 | 0.835 → 0.846 |
| Wrong answers given directly | 0.044 → 0.033 | 0.022 |
| Right answer within one tap | 0.945 → 0.956 | 0.956 → 0.967 |

## Needs a decision or a fact

- **Lost-card wording**: the fraud messages still say "block your card",
  but AB Bank offers no cards. What should a customer block (eTumba, the
  account)? PO / Ops.
- **Loans**: is the Agro Loan still offered; Trader Mobility terms; the
  interest rates to quote for Micro and SME loans. Loans team.
- **Transfers**: confirm the K20,000 eTumba limit and any Online Banking
  limits. Ops.
- **Content gaps** customers ask about with no answer yet: cheque books,
  school-fee / car / mortgage loans (not offered: a "we don't offer this"
  answer would help), reference letters. See the probe document.
- The decisions D17-D30 to initial.
