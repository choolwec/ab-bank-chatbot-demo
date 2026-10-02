# Conversation probe: what broke, what changed (02/10/2026)

> For the product owner. A round of testing the bot with realistic messages
> until it broke, then fixing it. All wording stays draft for Legal.

## How it was tested

Four sets of customer messages and two sets of multi-turn conversations,
written the way people in Zambia actually type: greetings around requests
("hi, where is the Kitwe branch"), text-speak ("hw r u", "wats ur number",
"open acc pls"), typos, ALL CAPS, Nyanja and Bemba words, run-on messages,
people describing their situation instead of naming a product ("I'm a market
trader and need money for stock"), and answers to the callback form as people
really give them ("my name is Mary Banda", "+260 977 123 456", "after 2pm").
Each set was run against the real bot; every failure was fixed and the set
re-run. Later sets were written fresh, not tuned on, to check the fixes
generalise.

| Set | Before | After |
|---|---|---|
| Round 1: 201 single messages | 162 | 196 |
| Round 1: 55 conversations | 38 | 55 |
| Round 2 (fresh): 85 single messages | 65 | 82 |
| Round 2 (fresh): 32 conversations | 25 | 32 |
| Round 3 (fresh): 50 everyday-banking messages | 40 | 48 |

What is left is acceptable (for example "I want a loan" gets "how to apply"
rather than the Loans menu). All 423 cases are now a permanent test,
`tests/test_natural_conversation.py`.

The held-out quality gates (which no fix was tuned on) improved:

| Gate | Character matcher | Hybrid matcher |
|---|---|---|
| Right answers given directly | 0.670 → 0.681 | 0.835 → 0.846 |
| Wrong answers given directly | 0.044 → 0.033 | 0.022 (same) |
| Right answer within one tap | 0.945 → 0.956 | 0.956 → 0.967 |

## The most important fixes

- **A fraud call was missed.** "I got a call from someone saying they are from
  AB Bank asking for my PIN" got "Sorry, I didn't catch that". Any person
  asking for a PIN, OTP or password now starts a fraud report.
- **The callback form stored anything as a name.** "my name is Mary Banda"
  was stored as "My"; "hello", "ok" and "why do you need my name?" were stored
  as names. It now takes the name out of the sentence and asks again for
  anything that is not a name, saying why it needs it.
- **Failed transactions got unrelated answers.** "My eTumba transaction
  failed" got eTumba fees; "money not received" got the ZESCO token steps. Both
  now ask "Would you like to make a formal complaint?".
- **"What documents do I need to open an account" gave the business
  documents.** It now gives the personal account list.

## What now works that did not

- Greetings with a request: "hi how are you", "hello I need help", "good
  morning, where is the Ndola branch".
- Small talk: "see you later", "good night", "fine thanks", "what's your
  name", "are you a bot", "you're very helpful", "your staff were great".
- Text-speak and typos: "hw r u", "thnx", "wats ur number", "tamnga acount",
  "lsk branch".
- "Tell me about Tamanga", "what about the savings plan".
- Questions about a product, named or just shown: "what is the minimum
  balance for Tamanga", "what's the interest rate?" after the Term Deposit,
  "how old must the child be?" after Kids Savings (all answered with the
  product's full details).
- Natural answers to "Would you like us to contact you?": "I'm interested",
  "contact me", "sure", "maybe later", "not now".
- "Tell me more", "more info", "go back", "the first one", "2nd", "option 2".
- Typing part of a button: "savings" for [Savings Account].
- Branches: "do you have a branch in Kabwe" (no branch: says so and lists the
  towns), "what time does the Ndola branch close" (that branch's hours).
- The callback form: "+260 977 123 456" and "call me on 0977…" stored as
  0977123456; "in the morning", "any time", "after 2pm" stored as Morning /
  Anytime / Afternoon; "change my number" or "the name is wrong" at the
  summary goes straight to that field.
- A message with a card or account number in it still gets its answer (after
  the warning about sharing numbers).

## Round 5: conversation flow (same day)

After the product owner removed the callback summary ("Here's what I'll
send" served no purpose after the consent question), a further round on how
conversations flow:

- Details given at once are kept and read back: "my name is Mary Banda,
  call me on 0977 123 456 in the afternoon" fills the whole form; so do
  "Mary Banda 0977123456" at the name step and "0977... anytime" at the
  phone step. "Yes, call me on 0966..." after a product starts the form with
  the product and the number.
- "I want to talk to someone about a loan" opens the callback with "Loans"
  as the topic (also "a tractor loan", "the SME loan", "opening an account").
- Recovering from a miss: "no, I meant savings" answers savings; "that's not
  what I asked" apologises, offers a person or the menu, and is logged for
  the weekly review.
- Closing: "no" after an answer gets "No problem. Anything else?"; "that's
  all", "bye" and "thank you, bye" get a proper goodbye; "bye" in the middle
  of the callback form leaves it.
- No pressure: "hmm, let me think", "not interested", "I'll come back
  later" after an offer get "No problem. I'm here whenever you're ready.",
  with the offer still one tap away.

## Content gaps found (no answer exists yet)

Customers asked these and the bot can only say it can't help or pass them to
a person. Worth adding answers once the facts are confirmed:

- ~~Cards, closing an account / KYC changes, transfers to other banks,
  deposits~~: answered since (product owner, 02/10/2026)
- **Cheque books** (only mentioned inside Tamanga Plus and Mukula Plus)
- **School fees, car and mortgage loans** (not offered, but customers ask:
  a "we don't offer this, here is what we do offer" answer would help)
- Reference letters for embassies and visas
- Nyanja and Bemba beyond greetings and thanks ("ndifuna kutsegula account"
  is only partly understood): see proposed ticket LG1

## For engineers

`CLAUDE.md` (Request pipeline and Free-text matching) lists each mechanism.
Matcher changes stay outside the scored index wherever possible (exact
phrases, greeting and lead-in stripping, the text-speak map), so they cannot
pull real questions their way. The held-out leak test now also covers
`exact_phrases`.
