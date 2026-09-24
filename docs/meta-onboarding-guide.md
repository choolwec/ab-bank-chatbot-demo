# Meta onboarding guide for bank admins (ticket W1)

> **Draft for the product owner to review**, with Marketing, the contact
> centre and Legal consulted. Written 24/09/2026. Meta changes its screens
> and rules often: steps marked **[VERIFY]** must be checked against Meta's
> own help pages on the day. Background is in `multi-platform-research.md`
> §5.1 and §5.2.

## Summary

Before the bot can answer on WhatsApp and Messenger, the bank needs, in
Meta's systems: a **bank-owned business portfolio**, **business
verification**, **one app** with the WhatsApp and Messenger products, a
**system user token**, a **registered WhatsApp number** with a payment
method, **approved templates**, and **Messenger App Review**. Most of this
is waiting time, so start in W01 (week of 28/09/2026). The target is to
finish by **W12 (18/12/2026)**.

This guide is for a non-technical bank admin. The developer only needs the
values listed in step 5 and step 8, delivered safely.

## Golden rules

- **Everything belongs to the bank**, never to a person or an agency. At
  least **two bank staff** are admins at all times.
- **Never paste a token, app secret or PIN into chat, email, Teams, a
  ticket, or an AI tool (including Claude).** Tokens go into the bank's
  password manager, and from there only into the production server's
  environment file.
- Names, addresses and websites must match the bank's **PACRA** documents
  **exactly**, letter for letter.

## Steps

### 1. Find or create the bank's Meta Business portfolio

1. Ask Marketing and the social team whether a Business portfolio already
   owns the AB Bank Zambia Facebook Page. Go to business.facebook.com and
   check **Settings → Business info** [VERIFY menu names].
2. If one exists, check who owns it. If an agency or a former employee owns
   it, ask for ownership to move to the bank (or for a bank admin to be
   added with full control) before doing anything else.
3. If none exists, create one using the bank's legal name and a shared bank
   email address (not a personal one).
4. Under **People**, make sure **at least two named bank staff** have full
   control. Record their names in the weekly status note.

*Done when:* two bank admins are named and the portfolio owns the Page.

### 2. Business verification

1. Go to **Security Centre** in Business settings and start verification
   [VERIFY location].
2. Enter the legal name, registered address, phone and website **exactly**
   as they appear on the PACRA certificate. A mismatch (for example "Ltd"
   against "Limited") is the most common reason for rejection.
3. Upload the documents Meta asks for (PACRA certificate of incorporation,
   and a utility bill or bank statement showing the address, if asked).
4. **Domain verification:** Meta will ask to verify abbank.co.zm. Ask the web
   team to add the DNS record or file Meta provides. It takes the web team a
   few minutes; plan for a few days of back and forth.
5. Wait. It can take from days to a few weeks. If rejected, read the reason,
   fix the mismatch and resubmit.

*Done when:* the verified status shows in Business settings.

### 3. Create the Meta app

1. Go to developers.facebook.com with a bank admin account, and create an
   app of type **Business** [VERIFY type name], connected to the bank's
   portfolio.
2. Name it plainly, for example "AB Bank Assistant".
3. Add two products: **WhatsApp** and **Messenger**.
4. Add the developer as an app developer or tester (not an admin).

*Done when:* the app exists under the bank's portfolio with both products.

### 4. System User and token

1. In Business settings, go to **Users → System users** and create a system
   user with the **Admin** role, named for example "assistant-server".
2. Assign it the app, the WhatsApp Business Account and the Facebook Page.
3. Generate a token that **does not expire**, with the permissions the
   developer lists [VERIFY names; expected to include WhatsApp messaging and
   management, and Page messaging].
4. **Copy the token straight into the bank's password manager.** Don't paste
   it anywhere else.
5. Also store the app's **App secret** (App settings → Basic) in the password
   manager.

*Done when:* token and app secret are in the password manager, visible to
the two admins and the developer only.

### 5. Hand the values to the developer, safely

The developer needs these as environment variables on the production
server. The admin enters them directly into the server's env file with the
developer, or shares the password-manager entry. **Never by email or chat.**

| Value | Env variable |
|---|---|
| System user token | `WA_ACCESS_TOKEN`, and the Page token for `MS_PAGE_TOKEN` [VERIFY whether one token serves both] |
| App secret | `WA_APP_SECRET`, `MS_APP_SECRET` |
| Phone number ID (step 8) | `WA_PHONE_NUMBER_ID` |
| Page ID, App ID | `MS_PAGE_ID`, `MS_APP_ID` |
| Webhook verify tokens | `WA_VERIFY_TOKEN`, `MS_VERIFY_TOKEN` (the developer generates these) |

### 6. The number decision

The bank already publishes **0769651262** as its WhatsApp number.

| Option | What it means | Main trade-off |
|---|---|---|
| **A. Migrate** | The number moves fully to the Cloud API; the bot and (later) Chatwoot handle everything | Business-app chat history is lost (back it up first); eligible for the free blue badge |
| **B. Coexistence** | Staff keep the WhatsApp Business app on the same number; the bot runs alongside and pauses when a person replies | No free blue badge; the app must be opened at least every 13 days [VERIFY] |
| **C. New number** | A separate number for the bot | Confuses customers and gives scammers a second "official" number |

**Recommendation:** **B for the pilot, then A** once the agent desk (H2) is
live. Confirm with Meta that moving from B to A later is supported
[VERIFY]. The PO records the decision (`decisions-log.md`).

*Done when:* the decision is signed in the decisions log.

### 7. Test number for staging

In the app's WhatsApp section, Meta provides a free **test number**. Add
up to five staff phones as test recipients [VERIFY limit], and point its
webhook at the staging server. The developer uses it from W06.

*Done when:* the developer confirms messages flow on staging.

### 8. Register the production number

1. In WhatsApp Manager, add the phone number (for option B, follow Meta's
   coexistence onboarding instead [VERIFY steps]).
2. Enter the **display name**: it must match the business name closely
   (for example "AB Bank Zambia"). Meta reviews it.
3. Set a **6-digit two-step verification PIN**. Store it in the password
   manager. It is needed to re-register the number.
4. Note the **Phone number ID** for the developer (step 5).

*Done when:* the number shows "Connected" and the display name is approved.

### 9. Payment method

Add a payment method to the WhatsApp Business Account (a bank card or
invoicing, with Finance). The research found that **from 1 October 2026
service messages are charged and aren't delivered without a payment method
on file** [VERIFY on Meta's pricing page]. Finance approves the monthly
budget (`execution-plan.md` §14).

*Done when:* the payment method shows as active.

### 10. Submit the three utility templates

Only **after Legal approves the wording** (L6). The wording is in
`knowledge/templates.yaml`:

- `case_received`
- `case_update`
- `callback_scheduled`

In WhatsApp Manager → **Message templates**, create each one with **exactly
the same name**, category **Utility**, language English, and the body from
the file. `{{1}}` is the case reference. Don't add links or promotional
words: Meta re-categorises such templates as marketing.

*Done when:* all three show "Approved".

### 11. Apply for the Official Business Account (blue badge)

Once the number is on the Cloud API (option A), verification is done and
2FA is set, request the Official Business Account in WhatsApp Manager
[VERIFY eligibility rules; some sources mention a minimum messaging tier].
If refused, the paid alternative is Meta Verified (decide with Finance).

*Done when:* the badge is approved, or the refusal and next step are
recorded.

### 12. Messenger App Review

Follow `docs/messenger-app-review.md`: it has the permissions, the
use-case text, reviewer steps and the screencast script. Legal's privacy
policy must be live first. Plan for one resubmission.

*Done when:* App Review is approved (`go-no-go.md` row 5.3).

## Checklist

| # | Step | Owner | Target week | Done when | Done (date / initials) |
|---|---|---|---|---|---|
| 1 | Bank-owned portfolio, ≥ 2 bank admins | PO + Marketing | W01 | Admins named in the status note | |
| 2 | Business verification, incl. domain | PO + web team | W01–W04 | Verified status showing | |
| 3 | Meta app with WhatsApp and Messenger | PO | W03 | App exists under the bank portfolio | |
| 4 | System User + non-expiring token | PO | W03 | Token and app secret in the password manager | |
| 5 | Values handed to the developer safely | PO + Dev | W03 onwards | Env file set; nothing sent by email or chat | |
| 6 | Number decision | PO + Marketing + CC | W04 | Signed in `decisions-log.md` | |
| 7 | Test number on staging | Dev | W06 | Messages flow on staging | |
| 8 | Production number, display name, 2FA PIN | PO | W10 | "Connected"; name approved; PIN stored | |
| 9 | Payment method | PO + Finance | W10 | Active in WhatsApp Manager | |
| 10 | Three utility templates (after L6) | PO + Legal | W11 | All "Approved" | |
| 11 | Official Business Account | PO | W11 (after option A) | Approved, or refusal recorded | |
| 12 | Messenger App Review | PO + Legal | End of W15 | Approved | |
