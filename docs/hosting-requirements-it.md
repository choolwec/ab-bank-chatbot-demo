# Hosting request to IT: AB Bank customer assistant

> **Draft for the product owner to hand to the bank's IT**, after review by
> Compliance and Legal. Written 24/09/2026. Legal points are stated as the
> project understands them and must be confirmed by Legal.

## The ask

Please host the customer assistant's backend on **one always-on virtual
machine inside Zambia**, reachable from the internet over HTTPS, by **W08
(16–20/11/2026)**. A second, similar VM will be needed for the agent desk
(Chatwoot) from about W17 (January 2027). If IT can't host it, we will ask
for quotes from Lusaka data centres instead (see "Fallback").

## Why it must be in Zambia

- The Data Protection Act No. 3 of 2021, **s.70**, requires personal data to
  be processed and stored on a server or data centre in Zambia (sensitive
  data only in Zambia). The assistant stores masked chat transcripts,
  tickets with customers' names and phone numbers, and session state.
  **Legal to confirm against the official text.**
- The Bank of Zambia's Cyber and Information Risk Management Guidelines
  (2023) cover third-party and outsourced hosting, which is one more reason
  to host with IT (Compliance ticket L4).
- The current demo on Render (outside Zambia) holds synthetic data only and
  will stay a staging system.

## What the application is

A small Python (FastAPI) web service, written in-house. No large language
model and no external AI service: everything, including a small language
model file (about 90 MB), runs locally on the VM. Data lives in three SQLite
files on local disk. It must run as **exactly one process** (it keeps
per-customer locks in memory).

## Specification

| Item | Requirement |
|---|---|
| VM | 2 vCPU, 4 GB RAM, 40 GB SSD. Always on (Meta resends webhooks for days if it is down) |
| OS | Ubuntu Server LTS (current release), with security updates applied |
| Software we install | Python 3.11, nginx, sqlite3, git; our systemd service runs as a non-root user |
| Network placement | DMZ, with a public DNS name (for example `assistant.abbank.co.zm` **[CONFIRM name with IT/web team]**) |
| Certificate | A valid, publicly trusted TLS certificate (the bank's, or Let's Encrypt). Meta refuses webhooks without one |
| Inbound | **TCP 443 only** from the internet (Meta's webhooks and customers' browsers loading the website widget). SSH only from the bank's admin network or VPN |
| Outbound | **TCP 443** to `graph.facebook.com` (WhatsApp and Messenger), to the Jira host (for example `<bank>.atlassian.net`, see note), to package mirrors for updates, and to `huggingface.co` during deploys only (the language model file is downloaded once and checked against a pinned hash). Later: the Chatwoot VM |
| Reverse proxy | nginx on the VM (config supplied in `deploy/`). If IT adds its own proxy or load balancer in front, tell us how many hops (we set `PROXY_HOPS`), and **don't rewrite request bodies** on `/webhooks/*` (Meta signs the raw body) |
| Backups | Nightly, of the SQLite files and the secrets file. Keep 14 days. **Copies stay in Zambia.** We supply `deploy/backup.sh`; IT's backup system is welcome instead. One test restore before launch |
| Monitoring | An uptime check on `https://<host>/health` from outside the network, alerting the project's Teams group chat (R1). CPU, disk and memory alerts from IT's tools if available |
| Logs | Application and nginx logs rotated with logrotate; kept on the VM for the retention period Legal sets |
| Time | NTP on; the app works in Lusaka time |

**Second VM (agent desk, from about January 2027):** similar size (Chatwoot
suggests about 4 GB RAM **[VERIFY against Chatwoot's current requirements]**),
same data-centre rules, reachable only from the bank's network by agents
and from the first VM.

## Who has access

| Who | Access |
|---|---|
| IT | Full administration of the VM, network and backups |
| Developer (named) | SSH as a deploy user with `sudo` for the app's service only; deploys release tags |
| Product owner and contact-centre lead | No shell by default. They need a way to flip the kill switches (one line in `flags.json`) out of hours: IT to advise (for example a restricted script run over SSH) |
| Secrets | The env file (`/etc/abz-chatbot/env`, root-only) holds Meta tokens, the Jira token, admin password and two encryption keys. Two named people keep a copy in the bank's password manager |

No vendor or third party needs access.

## Note on Jira

Tickets (with names, phone numbers and masked transcripts) are pushed to the
contact centre's Jira. If that Jira is Atlassian Cloud, it is hosted outside
Zambia. Legal is ruling on this separately (`legal-compliance-pack.md`); if
the answer is no, Jira stays switched off or moves to an in-country Jira
Data Center, and the outbound rule to Atlassian isn't needed.

## Fallback if IT can't host

Get quotes for a VM of the same spec from Tier III, ISO 27001 data centres
in Lusaka: **Paratus Lusaka, Infratel and MTN Lusaka**. Hosting outside
Zambia is **not** an option for real customer data. Compliance must still
approve the provider (L4).

## Timeline

| When | What |
|---|---|
| W01–W04 (by 23/10/2026) | IT says yes or no. If no, quotes requested at once |
| W05 (by 30/10/2026) | Contract, if external |
| **W08 (by 20/11/2026)** | VM delivered with DNS, certificate and firewall rules |
| W09–W10 | We deploy and test; two deploys, two rollbacks, one restore (P7) |
| W11 (07/12/2026) | Website launch, if the go/no-go passes |

## Contacts

Product owner: **[CONFIRM name]** · Developer: **[CONFIRM name]** ·
Compliance: **[CONFIRM name]**
