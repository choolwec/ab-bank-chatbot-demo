# Metrics at M1 (after Phase 1)

Generated 2026-09-23 at commit `13c1f0e` by `python -m admin.baseline_report`. Every later claim of improvement is measured against a report like this one.

## Understanding (E3 held-out set, production thresholds)

91 in-scope and 30 out-of-scope questions; direct answer at >= 0.7, suggestions at >= 0.45.

| Metric | Value | Gate | Target (excellence plan §1) |
|---|---|---|---|
| right_direct | 0.549 | >= 0.549 | >= 0.85 |
| wrong_direct | 0.044 | <= 0.044 | <= 0.02 |
| oos_direct | 0.267 | <= 0.267 | <= 0.03 |
| one_tap | 0.923 | >= 0.923 | — |
| oos_suggested | 0.733 | — | — |

Out-of-scope questions answered directly:

- 0.79 “i need a lawyer” → `loan_apply_how`
- 0.76 “how do i open a facebook account” → `account_opening_how`
- 0.72 “what documents do i need for a driving licence” → `account_opening_requirements`
- 0.77 “what time does shoprite close” → `opening_hours`
- 0.70 “how do i apply for a job at airtel” → `loan_apply_how`
- 0.72 “my whatsapp is not working” → `technical_issue`
- 0.74 “how do i reset my facebook password” → `credential_trouble`
- 0.74 “how do i apply for a passport” → `loan_apply_how`

In-scope questions answered with the wrong intent:

- 0.76 “tell me about tamanga” → `etumba_what_is` (expected `current_account`)
- 0.72 “what is this etumba thing” → `bot_capabilities` (expected `etumba_what_is`)
- 0.90 “where can i withdraw my etumba money” → `agent_locator` (expected `etumba_cash_in_out`)
- 0.81 “what security do you need for a loan” → `loan_requirements` (expected `collateral_definition`)

## Conversation and safety suites

| Suite | Result |
|---|---|
| E2 conversation scripts (`tests/test_conversations.py`) | 53 passed, 1 warning |
| S1 urgent detection (`tests/test_urgent.py`) | 141 passed, 1 warning |
| S3 red-team routing (`tests/test_redteam_routing.py`) | 44 passed, 1 warning |
| Full suite | 404 passed, 1 warning |

## Message budget per path

Bot bubbles the customer receives on the shortest happy path, not counting the welcome. Target: <= 4 bot messages per fraud report (M1).

| Path | Customer turns | Bot bubbles | Most bubbles in one turn |
|---|---|---|---|
| Fraud report (free-text trigger) | 4 | 4 | 1 |
| Fraud report (over-informative first message) | 3 | 3 | 1 |
| Fraud report (short trigger) | 5 | 5 | 1 |
| Lost card | 5 | 5 | 1 |
| Complaint | 5 | 5 | 1 |
| Callback request | 6 | 6 | 1 |
| Branch lookup | 3 | 3 | 1 |
| FAQ answer | 1 | 1 | 1 |
