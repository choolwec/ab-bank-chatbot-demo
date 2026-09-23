# V1 improvements from an external repo review — 2026-07-25

Six GitHub repos were reviewed for ideas to improve V1 specifically (not the
gated V2/LLM layer): `frogcoder/llm-chatbot` (an LLM+RAG "RBC AI Banking
Agent"), `worldbank/data-ai-chatbot` (Data360 Chat, a LangGraph/MCP data
assistant), `RasaHQ/financial-demo` (Rasa's banking demo bot),
`Jonathan-Tiede/Banking_Chatbot` (Dialogflow prototype),
`srishanthreddy456789/Finmate-AI-Assistance-Chatbot`, and
`CK-ghub/Banking-chatbot` (ChatterBot prototype). Most of these lean on
paid/cloud NLU or an LLM — not adoptable into V1's $0/local/deterministic
design — but a few patterns translated directly. What changed, and why:

## 1. Fraud flow now collects a contact number (real bug fix)

`app/flows/fraud.py` used to end with "a member of staff will contact you
as a priority" after collecting `what_happened` / `when` / `channel` —
**no phone number, no way to actually reach the customer.** Complaint and
lead flows both capture contact info; fraud, the single highest-priority
flow in the system, didn't. Added a mandatory, validated `contact` step
(same Zambian-phone validator the lead flow already used).

## 2. Confirm-before-submit (from RasaHQ/financial-demo + independent
convergence)

Rasa's financial demo confirms before executing a banking action, and
`Jonathan-Tiede/Banking_Chatbot`'s own README lists "addition of request
confirmations" as a known gap in its Dialogflow prototype — the same gap,
found independently. `FormFlow` (`app/flows/base.py`) now has a
`require_confirmation` flag: on for fraud/complaint/lead. Once all fields
are collected, the customer sees a summary with **Confirm / Edit my last
answer / Cancel** instead of the ticket submitting immediately. A typo'd
date or garbled detail can now be fixed before it reaches a human.

## 3. Mid-flow FAQ interrupt-and-resume (from RasaHQ/financial-demo)

Rasa's demo's headline dialogue feature is "limited ability to switch
skills mid-transaction and then return to the transaction at hand."
`router._maybe_answer_faq_interrupt` reproduces this narrowly: a
high-confidence, unrelated FAQ question asked mid-flow gets answered, then
the flow re-prompts the same step. This is **opt-in per field**
(`interruptible_fields` on the flow class), not opt-out — and deliberately
narrow, currently just fraud's `what_happened` and complaint's `details`.

Why so narrow: the first implementation applied it to every unvalidated
field and broke two flows in testing. "eTumba" — a legitimate answer to
fraud's `channel` step ("card, eTumba, internet banking, or a branch?") —
and "Opening a business account" — a legitimate callback `topic` — both
scored high-confidence against their own matching FAQ intents (etumba_what_is,
business_account) and got swallowed as "interruptions," desyncing the
flow's step counter. Fields whose *legitimate* answers are themselves
bank-topic words will always collide with this heuristic; only genuinely
narrative fields (describing an incident in your own words) are safe. Kept
the narrower version rather than abandoning the idea.

## 4. `/admin/jira-preview` auth gating (from worldbank/data-ai-chatbot)

That repo's internal `guardrails-audit.md` states two principles worth
copying: admin/operational routes should be config-driven allowlists, not
hardcoded, and every resource-accessing route should repeat the same
authorization pattern as its siblings. `/admin/jira-preview` had neither —
it was flagged as a known gap in this file already ("no auth yet"). Added
`ADMIN_TOKEN` (`config.py`), same env-var-driven pattern as the existing
`JIRA_*` secrets: unset keeps today's demo working with zero setup; once
set, `?token=...` must match (constant-time comparison) before the route
returns real customer data.

## 5. Extended the held-out phrase regression test

`tests/test_matcher.py::test_misspellings_and_zambian_english` already
existed as a held-out set (separate from each intent's own training
`phrases:` list) and had already caught one real misroute
(`credential_trouble` vs. the since-added `technical_issue`) before a demo.
Added ~12 more realistic Zambian-English/near-miss phrasings in the same
style, including a couple of close variants on the *already-fixed*
credential_trouble case to help guard the fix. One near-miss discovered
while writing these: `"cant log in to myabz"` is a **deliberate**
`credential_trouble` training phrase (routes to PIN-reset guidance), not
`technical_issue` — login-failure wording is genuinely ambiguous between
"forgot my PIN" and "the app is down," and the existing content made a
product call to default to the PIN-reset path. Recorded as a comment in
the test rather than silently overwritten, since it's a content decision,
not a bug.

## Not adopted, and why

Dialogflow, ChatterBot, Elasticsearch-based matching, and any
LangChain/Gemini-style LLM+RAG approach (the other four repos) all require
either a paid cloud NLU service or an LLM call — outside V1's $0/local/no
cross-border-data-transfer design by definition. Multilingual (Finmate's
Google Translate integration) and Duckling-style date/amount entity
extraction (Rasa) are real ideas but belong with V3 (Nyanja/Bemba) and a
future NLU upgrade respectively, not this pass.

## Test coverage added

`tests/test_flows.py`: fraud contact-capture regression test, confirm/edit
flow test, mid-flow FAQ interrupt test. `tests/test_admin.py` (new): the
three ADMIN_TOKEN states (unset/wrong/correct). Full suite: 86 passed.
