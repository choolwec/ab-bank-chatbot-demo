# Messenger App Review pack (ticket M1)

For the PO and Legal. Messenger's `pages_messaging` needs **Advanced Access**
before the bot can reply to the public rather than only to Page admins. Meta
rejects most often when the screencast doesn't match the stated use case, so
everything below matches what the bot actually does today (`app/channels/messenger.py`).
Plan for one resubmission. Items marked **[VERIFY]** must be checked against
Meta's current App Review screens when submitting.

## 1. What we ask for, and why

| Permission [VERIFY names] | Why the bot needs it | Where in the code |
|---|---|---|
| `pages_messaging` | Reply to people who message the Page, and hand the conversation to staff | `MessengerSender.send`, `pass_to_inbox` |
| `pages_manage_metadata` | Subscribe the webhook to `messages`, `messaging_postbacks`, `message_echoes`, `messaging_handovers`, `standby`, `feed`; set the Page profile | webhook, `admin/messenger_profile.py` |
| `pages_read_engagement` | Read new comments on the Page's posts, so an urgent one can get a private reply | `parse()` (feed changes) |
| `pages_manage_engagement` | Only if the PO turns on `MESSENGER_PUBLIC_REPLIES`: post the approved public line under an urgent comment | `public_reply` |
| Handover / conversation routing | Pass the thread to the Page Inbox (app 263902037430900) on "Talk to a person" | `pass_to_inbox` |

**Use-case statement (paste into the submission):**

> AB Bank Zambia's automated assistant answers customer questions about
> branches, accounts, eTumba and loans on our Facebook Page, takes fraud
> reports and complaints, and hands any conversation to our social-media team
> in the Page Inbox when the customer asks for a person. It tells customers it
> is automated in its first message and in the Page greeting. It never asks
> for PINs, passwords or card numbers, and it does not access accounts. When
> someone posts a public comment reporting fraud or a complaint, it sends one
> private message with the right next step. It sends no marketing.

## 2. Before submitting

- [ ] Business verification complete (shared with WhatsApp, W1).
- [ ] App in **Live** mode, webhook `https://<production host>/webhooks/messenger`
      subscribed, with `MS_APP_SECRET`, `MS_VERIFY_TOKEN`, `MS_PAGE_TOKEN`,
      `MS_PAGE_ID` and `MS_APP_ID` set.
- [ ] `python -m admin.messenger_profile --apply` has run: Get Started, greeting,
      persistent menu, ice breakers.
- [ ] **Privacy-policy URL** on abbank.co.zm is live (Legal writes it; §4).
- [ ] Page Inbox conversation routing: the bot app is the default receiver and
      the Page Inbox is the secondary receiver **[VERIFY current Business Suite screens]**.
- [ ] A **reviewer test user** exists (§3), with the Page role Meta asks for.

## 3. Reviewer instructions (paste into the submission)

1. Open the AB Bank Zambia Page and tap **Get Started**. The bot introduces
   itself as automated and shows the menu.
2. Tap **eTumba**. The bot answers with quick-reply buttons.
3. Type **"I lost my card yesterday at cairo branch"**. The bot gives the
   emergency number and asks one confirmation question ("You said this
   happened yesterday, involving your card. Is that right?"). Tap **Yes**, then
   send any Zambian-format number such as 0977 000 000. The bot confirms an
   urgent case with a reference (FRD-…).
4. Type **"talk to a person"**. The bot says a person will reply in the same
   conversation, gives a reference (HND-…), and passes the thread to the Page
   Inbox. It then stays silent while staff reply.
5. Comment **"someone stole money from my account"** on any Page post. The
   commenter receives one private message with the emergency number.

## 4. The privacy policy must cover (Legal)

- What the assistant collects: messages (with card, NRC, account and PIN
  numbers masked before storage), and contact details the customer chooses
  to give.
- That Meta processes Messenger messages as a processor, including outside
  Zambia (L2, DPA s.70/71), and the lawful basis.
- Retention of transcripts, tickets and sessions (L5; today's placeholders:
  `TRANSCRIPT_RETENTION_DAYS`, `TICKET_RETENTION_DAYS`).
- That identities are stored only as keyed hashes in logs; how to ask for
  access or deletion; the DPO contact.
- That the assistant is automated, and how to reach a person.

## 5. Screencast script (about 90 seconds, phone screen recording)

| Time | Show | Say / caption |
|---|---|---|
| 0:00 | The Page, tap Get Started | "Customers message AB Bank's Page. The assistant says it's automated." |
| 0:10 | Tap eTumba; the answer and quick replies | "It answers common questions from approved content." |
| 0:25 | Type the lost-card message; the confirmation; tap Yes; send the number; the reference | "Fraud and lost cards are treated as urgent. It never asks for PINs or card numbers." |
| 0:50 | Type "talk to a person"; the handover message | "Any time, the customer can reach a person." |
| 1:00 | Business Suite: the conversation in the Page Inbox, an agent replies | "Staff reply in the Page Inbox; the bot stays quiet." |
| 1:15 | Mark the conversation Done; the customer writes again; the bot answers | "When staff finish, the assistant takes over again." |
| 1:25 | A public comment "someone stole my money"; the private message | "Urgent public comments get one private message with the next step." |

Record on the production Page with the reviewer test user. Don't show any
real customer's data. Use the synthetic number above.

## 6. If it's rejected

Read the rejection against §1: it is usually one permission without a
matching moment in the screencast. Re-record only that part, reply in the
App Review thread, and resubmit. Keep each submission's screencast and notes
in the shared drive with the date.
