# Voice and tone: how the AB Bank assistant writes

For anyone editing `knowledge/intents/*.yaml` or `knowledge/system_messages.yaml`
(ticket K1). Every rule has a reason; if a rule gets in the way of being
clear, clarity wins, and tell the content owner so the guide can change.

## The rules

1. **Plain words.** Write so a primary-school reader understands on the
   first read. Short sentences, everyday words. Say "take money out", not
   "effect a withdrawal". If a banking word is unavoidable, explain it once:
   "collateral (something valuable you offer as security)".
2. **Key fact first.** Start with the answer, then the detail. "Tamanga
   costs ZMW 36 a month." comes before what the account is for.
3. **Three short paragraphs at most.** If it needs more, it needs a button
   to a second answer instead. People read this on a phone.
4. **One question per message.** Ask one thing, then wait. "What's your
   name?" and not "What's your name and number?". Every question the bot
   asks must be answerable by a button or a short typed reply.
5. **Never blame the customer.** "That doesn't look like a valid number"
   (about the number), never "You entered the wrong number" (about them).
   The bot says "I'm not getting this right", not "you are not clear".
6. **Fixed words for key terms.** Always write them exactly like this:

   | Write | Never |
   |---|---|
   | eTumba | Etumba, e-Tumba, E-tumba |
   | MyABZ | myABZ, My ABZ, MYABZ |
   | `*888#` (use `{ussd_code}`) | 888, *888 |
   | Tamanga, Tamanga Plus, Mukula Plus | tamanga, TamangaPlus |
   | ZMW 36 | K36, 36 kwacha, ZMW36 |
   | branch | office, outlet |

   Contact details always come from the `{placeholders}` (`{contact_phone}`,
   `{emergency_phone}`, `{tariff_url}` …), never typed in, so one change in
   `app/config.py` updates every answer.
7. **Honest about limits.** The bot is automated and says so. It never
   promises what it can't do: no "your money will be returned", no "I've
   blocked your card". It says who will do what, and when: "Our team will
   call you within one working day."

## Apologies

Apologise for the situation, not with grovelling, and follow the apology
with a way forward in the same message.

- Good: "I'm sorry this has happened. You've done the right thing by
  reporting it, and I'm treating it as urgent."
- Good: "I'm sorry — I can see this isn't working for you. A person from
  our team can help you directly."
- Avoid: "We sincerely apologise for any inconvenience caused." (says
  nothing, offers nothing)
- One apology per message, and not in every message. An apology in reply to
  a simple question sounds robotic.

## Fraud and complaints

- Urgent first: the number to call comes before anything the bot asks.
- Reassure without promising an outcome: "a person will follow up" is true;
  "you'll get your money back" may not be.
- Never ask for a PIN, password, OTP or full card number, and say so when
  it matters: "no genuine member of staff will ever ask for them."

## Short labels and plain versions

- **`short_label`** (20 characters or fewer) is required on every intent or
  button label longer than 20 characters. WhatsApp cuts buttons off at 20.
  Keep the meaning: "Tamanga Plus (premium current account)" becomes
  "Tamanga Plus". A test fails if one is missing.
- **`answer_simple`** is the plainer version sent when a customer asks "what
  do you mean?". Same facts only, never new ones, and shorter than the
  answer. No `[CONFIRM` placeholders: if the fact isn't confirmed, leave it
  out of the simple version.

## Before you commit

Run `pytest`. It checks every phrase still reaches its intent, every answer
has a button, every long label has a short one, and every plainer version is
shorter than its answer. Then regenerate the legal review
(`python -m admin.legal_export`): wording changes go to Legal before a
production release.
