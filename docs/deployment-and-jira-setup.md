# Deployment & Jira Setup — AB Bank Chatbot

Two things this bot needs that aren't running yet: a place for the backend
to live on the internet, and (optionally) a real connection to the contact
center's Jira. Neither one needs IT — both are written up here as a
standalone reference so they can be handed to whoever ends up owning each
piece (e.g. yourself for Render, the contact-center team for Jira).

---

## Part 1 — Hosting the backend (Render, free, no IT needed)

The chatbot has two halves: the **widget** (the chat button embedded on the
WordPress site — see `wordpress-plugin/README.md`) and the **backend** (the
Python app that actually understands messages and answers them). The
widget is just a script tag; it needs the backend running somewhere
reachable on the internet 24/7. Right now the backend only runs on a local
computer (`INSTRUCTIONS.md` §1), which stops working the moment that
computer is off or offline.

This repo is already set up to deploy for free on **Render** — no server
to manage, no IT ticket.

### Steps

1. Go to [render.com](https://render.com) and sign up for a free account,
   signing in with the GitHub account this project is already pushed to:
   `choolwec/ab-bank-chatbot-demo`.
2. **New → Web Service** → select this repo. Render reads the `render.yaml`
   file already committed at the root of the repo and fills in every
   setting itself (Python runtime, free plan, the correct start command) —
   nothing to type or configure by hand.
3. Click **Create Web Service**. The first deploy takes a few minutes.
   When it finishes, Render gives a public URL, e.g.
   `https://ab-bank-chatbot-demo.onrender.com`.
4. Still in the Render dashboard, open the service's **Environment** tab
   and add these two variables (see table below), then save — Render
   redeploys automatically.
5. Back in WordPress admin: **Settings → AB Bank Chatbot**, paste the
   Render URL from step 3, **Save**. See `wordpress-plugin/README.md` if
   the plugin itself isn't installed yet.

### Required environment variables on Render

| Variable | Value | Why |
|---|---|---|
| `ALLOWED_ORIGINS` | `https://abbank.co.zm` (the real WordPress domain, comma-separate if there's more than one, e.g. a staging URL) | Without this, the widget loads but every chat message is silently blocked by the browser (CORS). Defaults to `localhost` only. |
| `PROXY_HOPS` | `1` | Render puts every app behind its own edge proxy, so without this every visitor's messages would appear to come from Render's proxy IP — collapsing all real users into one shared 20-messages/minute rate limit bucket instead of one bucket each. |

Everything else (`JIRA_*`, retention days, etc.) can be added the same way
later — see Part 2 and `README.md`'s "Before launch" checklist.

### The one catch

Render's free tier puts the service to sleep after ~15 minutes with no
visitors; the next message after that takes ~30-50 seconds to wake it back
up. That's fine for a low-traffic pilot (under 100 users/month). If that
delay becomes a real problem once traffic grows, Render's cheapest paid
tier (~$7/month) removes it — a small, justifiable upgrade once the pilot
proves the bot is worth keeping, not a day-one cost.

---

## Part 2 — Connecting real Jira

The bot already pushes every fraud/complaint/callback ticket toward Jira
(`app/jira_export.py`) — right now in **mock mode**, writing fake tickets
(`CC-1`, `CC-2`, …) to `data/jira_mock.jsonl` because no real credentials
are set. Flipping it to real mode is four environment variables and **no
code change**.

| Variable | What it is | Where to get it |
|---|---|---|
| `JIRA_BASE_URL` | The Jira site's URL | The address bar when logged into Jira, e.g. `https://abbank.atlassian.net` |
| `JIRA_EMAIL` | Login email for the account the bot will act as | Whoever's account this is — see below |
| `JIRA_API_TOKEN` | An API token for that account | Self-generated at `id.atlassian.com/manage-profile/security/api-tokens` → **Create API token** (no admin approval needed, if the account already exists) |
| `JIRA_PROJECT_KEY` | The short prefix on ticket numbers in the target project | Visible on any existing issue, e.g. "CC" in "CC-123" |

**Who actually needs to be involved**: this may not require IT at all.
- If **someone on the contact-center team already has a Jira login** with
  permission to create issues in the target project, they can generate
  their own API token (the step above is self-service) and hand over
  those four values directly — no admin ticket required.
- IT (or whoever administers the Jira instance) is only needed if **no one
  has Jira access yet**, or the destination project doesn't exist — that
  part does require someone with Jira admin rights to create the project
  and/or grant access.

Worth asking the contact-center team directly first, since they're the
ones who'd already have a working login for their own queue.

### Before it goes live with real customer data

- `GET /admin/jira-preview` (the page that renders ticket previews) has
  **no authentication yet** — gate it before real tickets flow through,
  per `README.md`'s launch checklist.
- Set the four variables above the same way as `ALLOWED_ORIGINS` — via the
  Render dashboard's Environment tab if the backend is hosted there.
