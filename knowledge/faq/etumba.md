<!-- Source content for V2 RAG chunking (§4.1). V1 answers live in
     intents/*.yaml — keep the two in sync.
     Primary sources: Branch Staff FAQ Document + UPDATED - SOCIAL MEDIA
     RESPONSE TEMPLATE (12.08.2025). -->

# eTumba mobile wallet

eTumba is AB Bank Zambia's mobile wallet, for payments, transfers, bill
payments, and savings. It works on any phone via USSD (**\*888#**) — no
smartphone or internet connection needed — or via the eTumba app (Google
Play Store / App Store) if the customer prefers a smartphone app.

## What you can do with eTumba

- Send and receive money, including to/from Airtel Money, MTN Momo, and
  Zamtel mobile money
- Buy airtime on **MTN, Airtel, and Zamtel**
- Pay bills: **ZESCO** and water
- Save via **Yaka** (a savings sub-wallet, see below)
- Check your own balance
- Cash in/out at branches, at agents, or (cardless) at ATMs

AB Bank Zambia does not currently operate its own branded ATMs. The
"cardless withdrawal" flow below works at ATMs that support the
mobile-network-operator (MNO) cardless option, not an AB Bank-branded ATM
network. [SOCIAL MEDIA TEMPLATE — this distinction is stated explicitly:
"Please note that currently we do not have ATMs."]

## Registering

Two ways to register, and registering is separate from linking to a bank
account:

- **App**: download "eTumba" from the Google Play Store or App Store, or
- **USSD**: dial **\*888#** and follow the prompts

**Linking to an AB Bank account** (needed to move money between eTumba and
a bank account, e.g. "pull"/"push" funds) requires a branch visit with an
original ID (NRC/Passport/Driving Licence) — this step cannot be done
remotely.

## Fees

The eTumba "mobile levy" mentioned in staff/social-media guidance applies
to two transaction types: wallet-to-wallet, and wallet-to-other-AB-Bank-
account. [Branch Staff FAQ / SOCIAL MEDIA TEMPLATE — neither document
gives the actual percentage.]

[WEB, supplementary research] This is very likely a reference to Zambia's
statutory **Mobile Money Transaction Levy** (Act No. 25 of 2024, in force
from 2025), a government levy collected by mobile money providers on
behalf of the Zambia Revenue Authority (ZRA) on a sliding scale of
**0.04%–0.21%** of the transaction value — not a fee AB Bank sets or keeps.
This is a national tax rule, not AB Bank-specific, so confirm with
compliance before quoting an exact percentage as "AB Bank's fee." All other
eTumba charges are listed in the official tariff guide (not independently
verified in this pass — see `company.md` for why the bank's own website
could not be fetched directly).

[CONFIRM: eTumba transaction/daily limits — a heading for this exists in
the Social Media Response Template ("ETUMBA LIMITS (SUBJECT TO CHANGE)")
but no figures were captured under it; likely a table/image that didn't
extract as text. Get the actual limits from the source document owner or
ops before publishing a specific number.]

## Cash in / cash out

Deposit into or withdraw from an eTumba wallet at:

- Any AB Bank Zambia branch
- Kazang agents
- 543 Konse Konse agents
- Zoona agents
- ATMs (cardless — see steps below)

### Deposit cash at a Kazang / 543 Konse Konse / Zoona agent

1. Dial \*888#
2. Select option 3: transact with agent/ATM
3. Select option 3: deposit cash at Kazang, 543, or Zoona agent
4. Give the agent your phone number to deposit cash; wait for an SMS
   confirmation

### Withdraw cash at a Kazang / 543 Konse Konse / Zoona agent

1. Dial \*888#
2. Select option 3: transact with agent/ATM
3. Select option 2: withdraw from Kazang, 543, or Zoona agent
4. Enter your eTumba transaction PIN
5. You'll receive a 6-digit authorization PIN
6. Give your phone number and the 6-digit PIN to the agent, then collect
   your cash

### Withdraw cash at an ATM (cardless)

1. Select "Cardless"
2. Select "MNO"
3. Select "eTumba"
4. Enter your phone number
5. Enter the OTP received on your phone
6. Enter the amount
7. Enter your eTumba PIN

## Moving money between eTumba and your AB Bank account

### Pull funds (AB Bank account → eTumba wallet)

1. Dial \*888#
2. Select option 2: Get money
3. Select option 1: Pull from AB Bank account
4. Enter the amount
5. Select 1 to confirm
6. Enter your PIN

### Push funds (eTumba wallet → AB Bank account)

1. Dial \*888#
2. Select option 1
3. Select option 2
4. Enter your account number, then the amount
5. Enter your PIN

## Transfers to/from other mobile money wallets

### eTumba → Airtel Money

1. Dial \*888# → Option 1 (Send money) → Option 3 (send to mobile money)
   → Option 2 (Airtel Money)
2. Enter the recipient's phone number and the amount
3. Enter a reference (mandatory — any number is acceptable)
4. Enter your PIN to confirm

### eTumba → MTN Momo

1. Dial \*888# → Option 1 (send money) → Option 3 (send to mobile money)
   → Option 1 (MTN)
2. Enter the recipient's MTN Money number and the amount
3. Enter a reference (mandatory)
4. Enter your eTumba transaction PIN

### Airtel Money → eTumba

1. Dial \*115# → 1 (send money) → 4 (Banks) → 1 (transfer to bank)
   → select AB Bank
2. Enter your eTumba number and the amount
3. Confirm details and enter your PIN

### MTN Momo → eTumba

1. Dial \*115# → 1 (send money) → 5 (Other Wallets) → 4 (eTumba)
2. Enter your eTumba number and the amount
3. Enter a reference and your PIN

### Zamtel → eTumba

1. Dial \*115# → Option 1 (Send money) → Option 3 (Send to bank account)
   → Option 1 (eTumba by AB Bank)
2. Enter your eTumba phone number and the amount
3. Enter your PIN, then select 1 to confirm

### General mobile-money-to-bank transfer (e.g. Airtel/MTN → AB Bank account
directly, not via eTumba)

Airtel USSD: \*115# → 1 (Send Money) → 4 (Banks) → 1 (Transfer to bank)
→ 9 (AB Bank) → enter AB Bank account number, amount, and Airtel Money PIN.

MTN USSD: \*115# → Option 1 (Send Money) → Option 6 (Banks) → Option 1
(Send to Bank) → Option 5 (AB Bank) → enter account number, amount, and
reference.

[Menu option numbers for a given operator can change on the operator's own
USSD menu, not AB Bank's — reconfirm periodically rather than treating
these as permanently fixed.]

### Reversing a wrongly sent transfer

If money was sent to a number that isn't on eTumba:

1. Dial \*888# → Option 1 (send money) → Option 5 (view pending)
2. Select 3, then the number the money was sent to
3. Select option 1 to cancel the request, and enter your PIN to authorize
   the cancellation

## Yaka savings

Yaka is a savings sub-wallet inside eTumba, letting you move funds between
your eTumba main balance and Yaka Savings.

- Interest: **5% per annum**, credited monthly

To open:
1. Dial \*888#
2. Select option 6
3. Choose option 1
4. Enter your PIN to authenticate
5. Select "Yaka Savings" to register

## Retrieving a ZESCO token after paying via eTumba

**Via USSD**: Dial \*888# and select 8 → "View Accounts/Transactions" (1)
→ "View eTumba transactions" (2) → Outgoing Transactions → enter PIN →
select the ZESCO payment to see the token in the details.

**Via the eTumba app**: "View Accounts & Transactions" → "View eTumba
transactions" → tap the ZESCO payment to find the token.

## When eTumba is down

If the USSD service or a specific transfer route (e.g. eTumba↔Airtel) is
temporarily unavailable, tell the customer it's a known, temporary issue
being worked on, apologise for the inconvenience, and — if it's the USSD
side specifically — suggest the eTumba app as an alternative channel while
USSD is down. Don't speculate on a fix time; that's a "what NOT to say"
timeline risk (see `loans.md`'s risk-box guidance, which applies equally
here).
