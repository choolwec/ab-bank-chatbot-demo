# Marketing launch kit: driving traffic and leads to the assistant

For Marketing, with Legal/Compliance and the product owner (tickets MK1–MK6).
**Everything in this kit is a draft.** No copy below may be published until
Legal/Compliance has reviewed it, and every `[CONFIRM …]` is a bank fact that
its owner must confirm first. `[VERIFY]` marks an external or platform fact
(Meta, the law) that must be checked against the official source. A qualified
person reviews every piece before it goes out.

## Summary

- The assistant generates leads through its **callback request**: every
  product answer (accounts, savings, loans, fees, eTumba) offers "Request a
  callback" or "Talk to a person" in one tap.
- Each callback lands in the contact centre's **Jira** queue. When the
  customer agreed to news and offers, it carries the label
  **`marketing-consent`**. Marketing works from a Jira filter; there is **no
  bulk export** of leads, so personal data stays in one controlled place.
- Every campaign gets a short **campaign code** (for example `cairo01`). It
  travels with the visitor from the website or a WhatsApp QR code to the
  callback ticket, so each campaign's leads can be counted.
- **Do not send marketing messages over WhatsApp or Messenger** to anyone who
  has not opted in. For the multi-channel launch, the recommendation stands:
  no outbound marketing at all, only replies to customers who wrote first
  (`docs/multi-platform-research.md` §3.4).

## 1. Where traffic can come from

| Route | How it works | Campaign code travels as |
|---|---|---|
| Website widget | The chat button on abbank.co.zm | `data-campaign` on the widget's script tag, or `utm_campaign` / `utm_source` in the page URL |
| Website "Continue on WhatsApp" link | A link in the widget header, shown once WhatsApp is live (`WA_LINK_ENABLED`) | `ref:<code>` in the prefilled WhatsApp message (default `ref:website`) |
| Branch QR poster | A QR code that opens WhatsApp with a prefilled message | `ref:<code>` in the prefilled message |
| Social posts and ads | A link to the website page with the widget, or a wa.me link | `utm_*` on website links; `ref:<code>` on wa.me links |
| Facebook Page | The Page's Messenger button and its WhatsApp call-to-action button | Not tracked by code yet (see §7) |

### Campaign codes

- Letters, digits, `_` and `-` only, **at most 40 characters**. Anything else
  is removed, and codes are stored in lower case (`CAIRO01` and `cairo01` are
  the same campaign).
- **Never put personal data in a code.** A code with 7 or more digits in a
  row is rejected outright, in case it is a phone or account number.
- Keep a simple naming scheme, for example `<channel>-<place or offer>-<yymm>`:
  `qr-cairo-2611`, `fb-savings-2611`, `web-banner-2611`.
- Keep a register of codes (who, what, when) in the Marketing team's own
  files, so the weekly numbers can be read later.
- The first code a conversation carries is the one that counts (first-touch
  attribution). A later code in the same conversation is ignored.

### Links

- **Website page with a code:**
  `https://www.abbank.co.zm/<page>?utm_source=facebook&utm_campaign=fb-savings-2611`
  [CONFIRM: the page the widget is embedded on]. `utm_campaign` wins over
  `utm_source` when both are present.
- **Website embed with a fixed code** (a landing page for one campaign):
  `<script src="https://<host>/widget/widget.js" data-campaign="web-banner-2611" defer></script>`
- **WhatsApp link with a code:**
  `https://wa.me/260769651262?text=Hi%20ref:qr-cairo-2611`
  [CONFIRM: the official WhatsApp number for public use]. The customer sees
  "Hi ref:qr-cairo-2611" in their message box and taps send. The bot removes
  the `ref:` part before reading the message, so it never changes the answer,
  and replies to "Hi" with its greeting.
- **QR codes:** encode the WhatsApp link above. Use any QR generator that
  does not add its own tracking redirect; the QR code should contain the
  wa.me address itself, so a customer can see where it goes before opening it.

## 2. Consent and opt-out rules (read before any campaign)

These rules come from the Electronic Communications and Transactions Act 2021,
the Data Protection Act 2021 and Meta's policies. Legal must confirm how they
apply to AB Bank before launch [VERIFY with Legal].

1. **Opt-in first.** Send marketing only to customers who said yes to news
   and offers. In the chat, that is the optional last question of a callback
   request: "may AB Bank send you news and offers…". The answer, and when it
   was given, go on the Jira issue (`marketing_consent: yes`,
   `marketing_consent_at: <UTC time>`).
2. **The callback goes ahead either way.** Consent is never a condition of
   being called back.
3. **A working opt-out, every time.** Customers can type "unsubscribe", "opt
   out", "stop offers" or "stop marketing" at any point. The bot confirms,
   records `action=marketing_opt_out` (with the customer's anonymous
   `user_hash`, never a phone number) and never asks the question again in
   that conversation. Every marketing message must say how to opt out.
4. **Honour opt-outs everywhere.** Before a campaign goes out, check the
   opt-out count in the weekly report and ask the chatbot administrator to
   match WhatsApp opt-outs against the list [CONFIRM: owner of the
   suppression process]. A customer who opts out through any channel must
   stop receiving marketing through all of them [VERIFY with Legal].
5. **Purpose limitation.** A phone number given for a callback is used for
   that callback. It may be used for marketing only when the same ticket says
   `marketing_consent: yes` [VERIFY with Legal: whether one consent covers
   calls, SMS, email and WhatsApp, or each needs its own].
6. **No marketing through WhatsApp or Messenger without opt-in.** Meta's
   policies require it, and the Act makes a missing opt-out an offence
   [VERIFY].
7. **WhatsApp templates:**
   - Messages to a customer more than 24 hours after their last message need
     an approved template.
   - **Marketing templates** need the customer's opt-in and cost more per
     message than utility templates (about US$0.0225 each in Meta's "Rest of
     Africa" rates [VERIFY current rate card]).
   - **Utility templates** (case updates such as `case_update`) must contain
     no promotional wording at all. Meta re-categorises a utility template
     with promotional language as marketing [VERIFY], and Legal approves the
     wording (L6).
   - A chat that starts from a Click-to-WhatsApp ad or the Facebook Page's
     WhatsApp button opens a 72-hour window of free service messages
     [VERIFY]. That window is for answering the customer, not for marketing.
8. **Personal data stays in Jira.** No spreadsheets of names and numbers.
   Filter in Jira, work the lead there, and record the outcome there.

## 3. Draft copy

All copy is **draft, requiring Legal/Compliance review**. Replace every
`[CONFIRM …]` before use. Keep the anti-scam message on every piece that
mentions WhatsApp.

### 3.1 Announcing the official number

> **AB Bank is now on WhatsApp.**
> Chat with us on our one official number: **[CONFIRM: +260 76 965 1262]**.
> Ask about accounts, loans, eTumba and branches, or ask for a call back,
> any time. Our assistant is automated and will connect you to a person when
> you need one.
> Look for the name **[CONFIRM: approved WhatsApp display name]** and the
> green verified badge [VERIFY: whether a verified badge will be granted].
> AB Bank will never ask for your PIN, OTP or password.

### 3.2 Anti-scam message

> **Protect yourself from scams.**
> - AB Bank will **never** ask for your PIN, OTP (one-time password) or
>   internet banking password, on WhatsApp, by phone, by SMS or in person.
> - We have **only one** official WhatsApp number: **[CONFIRM: +260 76 965
>   1262]**. Any other number using our name is not us.
> - We will never send you a link asking you to "verify" your account.
> - If someone asks for these details, stop, and call us on **888**
>   [CONFIRM: 24-hour card-block line, if one exists].
> - Lost your card or think you've been scammed? Tell us straight away on
>   WhatsApp or call **888**.

### 3.3 Branch QR poster

> **Questions? Chat with AB Bank on WhatsApp.**
> Scan to open WhatsApp and say hi.
> [QR code: `https://wa.me/260769651262?text=Hi%20ref:qr-<branch>-<yymm>`]
> Accounts · Loans · eTumba · Branches · Call-back requests
> Our one official number: **[CONFIRM: +260 76 965 1262]**
> We will never ask for your PIN, OTP or password.
> *Standard data charges from your mobile network may apply [VERIFY with
> Legal: whether this line is needed].*

Print one poster per branch with its own code (for example
`qr-cairo-2611`), so the weekly report shows which branches drive chats.

### 3.4 Website banner

> **Get answers in seconds, day or night.**
> Ask our assistant about accounts, loans and eTumba, or ask us to call you
> back. [Chat now]
> *An automated assistant. A person from our team is one tap away.*

Link the button to open the widget, or to a landing page whose widget tag
carries `data-campaign="web-banner-<yymm>"`.

### 3.5 Social posts

Post 1: launch

> Need to know which account suits you, or how to apply for a loan? Chat
> with AB Bank on WhatsApp: **[CONFIRM: +260 76 965 1262]**, our only
> official number. We will never ask for your PIN or OTP.
> [link: `https://wa.me/260769651262?text=Hi%20ref:fb-launch-<yymm>`]

Post 2: call back

> Prefer to talk it through? Ask our assistant for a call back and our team
> will ring you [CONFIRM: "within one working day" is the promise the bot
> makes]. Chat on our website or WhatsApp.
> [link: website page with `?utm_source=facebook&utm_campaign=fb-callback-<yymm>`]

Post 3: anti-scam

> Scam alert: AB Bank will never ask for your PIN, OTP or password. Our one
> official WhatsApp number is **[CONFIRM: +260 76 965 1262]**. If in doubt,
> call **888**.

Do not name rates, fees or offers in posts unless the product owner has
confirmed the figures for that date [CONFIRM: current rates and fees].

## 4. Measuring campaigns

### Weekly report

`python -m admin.report --days 7` now ends with a **Campaigns** section:

| Column | Meaning |
|---|---|
| Source | The campaign code (`unknown` when there was none) |
| Sessions | Conversations that started with that code |
| Callbacks | Callback requests from those conversations |
| Callbacks with marketing consent | Of those, how many said yes to news and offers |

It also shows the number of **marketing opt-outs** in the period. The report
holds counts only, never names or numbers. Useful ratios: callbacks ÷
sessions per code (how well a campaign converts) and consent ÷ callbacks (how
many leads Marketing may contact again).

### Jira

Every callback issue's description lists `source`, `marketing_consent` and
`marketing_consent_at`. Suggested filters (JQL) [VERIFY against the project's
Jira set-up]:

- Leads Marketing may contact:
  `project = <KEY> AND labels = chatbot AND labels = marketing-consent`
- Callbacks from one campaign:
  `project = <KEY> AND labels = callback AND text ~ "\"source: qr-cairo-2611\""`
- This month's chatbot callbacks:
  `project = <KEY> AND labels = callback AND created >= startOfMonth()`

Record the outcome (called, account opened, loan applied) on the Jira issue
itself so conversion can be counted later without copying data out.

## 5. Switches and settings

| Setting | Default | What it does |
|---|---|---|
| `MARKETING_CONSENT_ENABLED` | `true` | Asks the consent question in callback requests. Off: the question is skipped and the ticket says `marketing_consent: not_asked`. |
| `WA_LINK_ENABLED` | `false` | Shows "Continue on WhatsApp" in the website widget. Turn on only when WhatsApp is live (W10 limited public pilot). |
| `WA_LINK_NUMBER` | `260769651262` | The number the link opens [CONFIRM: official number decision]. |

Both flags follow the usual kill-switch rule: an environment variable wins
over `flags.json`, which wins over the default, with no restart needed.

## 6. Launch checklist

- [ ] Legal/Compliance approve the consent question, the opt-out reply and
      every piece of copy in §3 (ECT Act 2021, Data Protection Act 2021).
- [ ] Every `[CONFIRM …]` above resolved by its owner.
- [ ] The official WhatsApp number and display name approved (W10) before any
      QR code is printed.
- [ ] A named owner for the opt-out suppression process (§2 rule 4).
- [ ] Campaign-code register set up.
- [ ] Jira filters saved for Marketing, with access limited to the people who
      work the leads.
- [ ] First weekly report reviewed with the contact centre after one week.

## 7. Not built yet

- **Messenger campaign codes.** m.me links can carry a `ref` parameter that
  arrives as a referral event [VERIFY]; the Messenger adapter does not read it
  yet, so those conversations show as `unknown`.
- **Cross-session opt-out on the website.** A website visitor is anonymous,
  so an opt-out there applies to that conversation only. WhatsApp
  conversations keep the opt-out for as long as the session is kept.
- **Outbound marketing.** Nothing in the bot sends marketing. Any future
  campaign sent through WhatsApp needs approved marketing templates, a budget
  and a Legal sign-off first.
