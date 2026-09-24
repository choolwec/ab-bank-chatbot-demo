# Production runbook: the Lusaka VM

**Summary.** How the chatbot runs in production (ticket P7): what IT must
provide, the first install, deploying a release tag, rolling back, restoring
a backup, rotating each secret, and every environment variable. The files it
refers to are in `deploy/`. Written 2026-09-24 against the build half of P7.
Nothing here has run on the real VM yet: acceptance (two deploys, two
rollbacks, one restore, `/health` green from outside) waits for the VM.
Treat it as a draft for IT and IT Security to review.

Decisions this runbook assumes (confirm or change before go-live):

| Decision | Choice |
|---|---|
| Hosting | An Ubuntu LTS VM in Zambia, preferably from the bank's own IT; fallback a Lusaka Tier III data centre. Nothing in `deploy/` is specific to either. |
| Process model | One uvicorn worker behind nginx on the same VM (CLAUDE.md: session locks, rate limits and the webhook worker live in process memory). |
| Releases | Only tags named `vMAJOR.MINOR.PATCH` (optionally `-rcN`) are deployed; `deploy.sh` refuses anything else. |
| Data and secrets | Outside the code: `/var/lib/abz-chatbot/data` and `/etc/abz-chatbot/`, so a deploy or rollback never touches them. |
| Kill switches | `/etc/abz-chatbot/flags.json` (`ABZ_FLAGS_FILE`), editable without a restart, and not reset by a deploy. |
| Backups | Nightly, encrypted with `age` to a key held off the VM, 14 days on the VM, copied off the VM inside Zambia. |

---

## 1. What IT must provide

| Item | Requirement |
|---|---|
| VM | Ubuntu 24.04 LTS (or the LTS IT supports), 2 vCPU, 4 GB RAM, 40 GB SSD, always on. Location in Zambia. [CONFIRM: Legal on the data-residency requirement] |
| Public access | A public DNS name [CONFIRM: host name] and HTTPS (443) plus HTTP (80, redirect and Let's Encrypt) reaching the VM in the DMZ. |
| Admin access | SSH only from the bank's admin network or VPN, one named account per person with `sudo`, no shared root login. |
| Outbound, always | `graph.facebook.com:443` (WhatsApp and Messenger sends); the Jira site on 443 once real Jira is on; the alert destination (R1). |
| Outbound, deploys only | GitHub (the repository), `pypi.org` and `files.pythonhosted.org` (pip), `huggingface.co` and its download CDN (the embedding model, first install or model change only) [VERIFY: the CDN host names Hugging Face redirects to], Ubuntu mirrors, and Let's Encrypt if used. If outbound goes through a proxy, set it for root in `/etc/environment`, `/etc/pip.conf` and git. |
| Inbound from Meta | Webhooks arrive from Meta's servers. Don't IP-filter them unless IT maintains Meta's published ranges; the signature check is the control. |
| TLS certificate | The bank's certificate (full chain and key), or Let's Encrypt via certbot. |
| Backup destination | Inside Zambia: an SSH/rsync target or a mounted share, keeping 14 days itself. [CONFIRM: destination, IT] |
| Backup key | An `age` key pair. Only the public key goes on the VM; the private key is held off the VM. [CONFIRM: key custodian] |
| Uptime check | An external check of `https://<host>/health` every minute. [CONFIRM: which tool, and who it pages] |
| Clock | NTP on, time zone `Africa/Lusaka`. |

Packages: `python3 python3-venv git nginx sqlite3 curl rsync age`, plus
`certbot` for Let's Encrypt.

## 2. Layout on the VM

| Path | Owner, mode | What |
|---|---|---|
| `/opt/abz-chatbot/repo.git` | root | Bare clone of the repository; only tags are fetched from it. |
| `/opt/abz-chatbot/releases/<tag>/` | root, read-only to the app | One tested release each, with its own `.venv`. The newest 5 are kept. |
| `/opt/abz-chatbot/current`, `previous` | root | Symlinks: the running release, and where `rollback.sh` goes. |
| `/opt/abz-chatbot/models/` | root | The embedding model, shared by releases (`EMBED_MODEL_DIR`). |
| `/etc/abz-chatbot/env` | root, 600 | Every secret and setting (`deploy/env.example`). |
| `/etc/abz-chatbot/flags.json` | root:abz, 640 | Kill switches. |
| `/etc/abz-chatbot/backup.conf` | root, 600 | Backup settings (`deploy/backup.sh` header). |
| `/var/lib/abz-chatbot/data/` | abz, 700 | `audit.db`, `sessions.db`, `inbox.db`, `audit.jsonl`. The only path the service can write. |
| `/var/backups/abz-chatbot/` | root, 700 | Nightly archives, 14 days. |
| `/var/log/abz-chatbot/` | root | `deploy.log`, `test-<tag>.log`, `backup.log`. |

The service runs as the system user `abz`. The databases hold the names and
phone numbers customers give in the callback, complaint and fraud flows
(session state and ticket fields), so the data directory and every backup
hold personal data. That is why backups are encrypted.

## 3. First install

Commands run as root (`sudo -i`). `v1.0.0` stands for the first release tag.

1. **Packages and clock.**
   `apt install python3 python3-venv git nginx sqlite3 curl rsync age`
   and `timedatectl set-timezone Africa/Lusaka`.
2. **User and folders.**
   ```
   useradd --system --home-dir /var/lib/abz-chatbot --shell /usr/sbin/nologin abz
   install -d -m 755 /opt/abz-chatbot /opt/abz-chatbot/releases /opt/abz-chatbot/models /var/log/abz-chatbot
   install -d -m 750 -o root -g abz /etc/abz-chatbot
   install -d -m 700 /var/backups/abz-chatbot
   ```
3. **Repository (read-only deploy key).**
   ```
   ssh-keygen -t ed25519 -N "" -f /root/.ssh/abz_deploy
   ```
   Add `/root/.ssh/abz_deploy.pub` as a read-only deploy key on the
   repository, then:
   ```
   GIT_SSH_COMMAND="ssh -i /root/.ssh/abz_deploy" git clone --bare git@github.com:choolwec/ab-bank-chatbot-demo.git /opt/abz-chatbot/repo.git
   git --git-dir=/opt/abz-chatbot/repo.git config core.sshCommand "ssh -i /root/.ssh/abz_deploy"
   git --git-dir=/opt/abz-chatbot/repo.git archive v1.0.0 deploy flags.json | tar -x -C /root --one-top-level=abz-bootstrap
   ```
   [CONFIRM: whether the repository moves to a bank-owned GitHub organisation first]
4. **Environment file.**
   `install -m 600 -o root -g root /root/abz-bootstrap/deploy/env.example /etc/abz-chatbot/env`,
   then fill in every line under "Required" (section 8 lists them all):
   `ABZ_DATA_DIR=/var/lib/abz-chatbot/data`,
   `ABZ_FLAGS_FILE=/etc/abz-chatbot/flags.json`,
   `EMBED_MODEL_DIR=/opt/abz-chatbot/models/all-MiniLM-L6-v2`, `PROXY_HOPS=1`,
   `ALLOWED_ORIGINS=<the bank's website>`, and two new secrets:
   - `USER_KEY_SECRET`: `openssl rand -hex 32`
   - `REPLY_KEY`: `openssl rand -base64 32 | tr '+/' '-_'` (a Fernet key)

   Set `ADMIN_USER` and `ADMIN_PASSWORD` (`openssl rand -base64 24`) to use
   the staff pages. Leave every optional line commented out unless you set it.
5. **Kill switches.** `install -m 640 -o root -g abz /root/abz-bootstrap/flags.json /etc/abz-chatbot/flags.json`.
   Set `"JIRA_ENABLED": false` unless the four `JIRA_*` values are real:
   mock mode writes names and numbers to a local file. [CONFIRM: PO]
6. **Service.**
   ```
   install -m 644 /root/abz-bootstrap/deploy/abz-chatbot.service /etc/systemd/system/
   systemctl daemon-reload && systemctl enable abz-chatbot
   ```
7. **First deploy.** `/root/abz-bootstrap/deploy/deploy.sh v1.0.0` (section 4).
   From then on, run the scripts from `/opt/abz-chatbot/current/deploy/`.
8. **nginx and TLS.** Install the site, then replace `chatbot.example.zm`
   in `/etc/nginx/sites-available/abz-chatbot` with the host name:
   ```
   install -m 644 /opt/abz-chatbot/current/deploy/nginx.conf /etc/nginx/sites-available/abz-chatbot
   ln -s ../sites-available/abz-chatbot /etc/nginx/sites-enabled/abz-chatbot
   rm -f /etc/nginx/sites-enabled/default
   ```
   - Bank certificate: put the full chain and key in
     `/etc/ssl/abz-chatbot/fullchain.pem` and `privkey.pem` (key root, 600).
   - Let's Encrypt: before enabling the site, run
     `certbot certonly --standalone -d <host>` (port 80 free), point the two
     `ssl_certificate` lines at `/etc/letsencrypt/live/<host>/`, then switch
     renewals to the webroot the site serves
     (`certbot reconfigure --webroot -w /var/www/letsencrypt --deploy-hook "systemctl reload nginx"`
     [VERIFY: `certbot reconfigure` on the installed certbot version]).

   Then `nginx -t && systemctl reload nginx`. Add the staff network to the
   `/admin/` block once IT names it.
9. **Logs and schedule.**
   ```
   install -m 644 /opt/abz-chatbot/current/deploy/logrotate.conf /etc/logrotate.d/abz-chatbot
   install -m 644 /opt/abz-chatbot/current/deploy/crontab.example /etc/cron.d/abz-chatbot
   ```
   Cap the journal: `/etc/systemd/journald.conf.d/abz.conf` with
   `[Journal]`, `MaxRetentionSec=30day` and `SystemMaxUse=1G`, then
   `systemctl restart systemd-journald`.
10. **Backups.** Create `/etc/abz-chatbot/backup.conf` (root, 600):
    ```
    BACKUP_AGE_RECIPIENT=age1...        # the public key only
    OFFSITE_DEST=<user>@<host>:<path>   # or a mounted path
    ```
    For an SSH destination, create `/root/.ssh/abz_backup` (as in step 3),
    install its public key on the destination, and accept the host key once
    with `ssh -i /root/.ssh/abz_backup <user>@<host>`. Run
    `/opt/abz-chatbot/current/deploy/backup.sh` once and check the archive
    arrived.
11. **Check.**
    - `curl -s https://<host>/health` from outside the bank's network;
    - `systemctl status abz-chatbot`, `journalctl -u abz-chatbot -n 50`;
    - `systemd-analyze security abz-chatbot`: note the exposure score in the
      acceptance record.
12. **Meta.** Once W1 is done, set the webhook URLs in the Meta app
    (`https://<host>/webhooks/whatsapp` and `/webhooks/messenger`) with the
    verify tokens from the env file.

## 4. Deploy a release

1. On a development machine, tag a commit on `master` whose CI run is green,
   and push the tag:
   `git tag -a v1.4.0 -m "v1.4.0: <what changed>"`, then `git push origin v1.4.0`.
2. On the VM: `sudo /opt/abz-chatbot/current/deploy/deploy.sh v1.4.0`.

`deploy.sh` fetches the tag, builds `releases/v1.4.0` with its own virtualenv,
runs `pip install -r requirements.txt` and `python -m admin.fetch_model`, and
runs the full test suite as `abz` on a scratch data directory with none of
the production environment. Only if the tests pass does it check the env
file, switch `current`, restart the service and wait up to 60 seconds for
`/health`. If `/health` fails it switches straight back and says so.

- Tests failed: nothing changed. The full output is in
  `/var/log/abz-chatbot/test-v1.4.0.log`.
- A tag that moved after it was built is refused. Make a new tag instead.
- Content edits are deploys too (CLAUDE.md): they follow the same path.

Every deploy and rollback is logged in `/var/log/abz-chatbot/deploy.log`
with the tag, commit and the `sudo` user.

## 5. Roll back

- To the release the last deploy replaced:
  `sudo /opt/abz-chatbot/current/deploy/rollback.sh`
- To any tested release still on disk (`ls /opt/abz-chatbot/releases`):
  `sudo /opt/abz-chatbot/current/deploy/rollback.sh v1.3.0`

A rollback only switches symlinks and restarts: it takes seconds. Running it
twice returns to where you started. All releases share the data directory;
schema changes are additive (`audit._MIGRATIONS` adds columns, older code
ignores them), so an older release reads today's data. A release whose notes
say its change is not additive needs a restore instead. Kill switches and
secrets are not affected.

## 6. Restore a backup

When data is lost or damaged, or when rebuilding the VM.

1. Choose the archive: `/var/backups/abz-chatbot/abz-<time>.tar.gz.age`, or
   copy one back from the off-VM destination with its `.sha256` file.
2. Get the `age` private key from its custodian onto the VM, root-only.
3. `sudo /opt/abz-chatbot/current/deploy/restore.sh <archive> <key file>`
4. Delete the key file: `shred -u <key file>`.

`restore.sh` checks the checksum and every database's integrity before it
touches anything. It then stops the service, renames the live data directory
to `data.pre-restore-<time>` (it never deletes it), puts the backup's
databases and key files in place, starts the service and waits for `/health`.
The backup's env file and `flags.json` are left in `/root/abz-restore-<time>/`
to compare; they are not applied.

- **Rebuilding the VM:** first-install steps 1 to 3, then install the env file
  and `flags.json` from the backup (extract the archive by hand, or run
  `restore.sh` once on a scratch VM), deploy the same tag that was running,
  then restore.
- **The backup is older than the last `REPLY_KEY` rotation:** add the
  backup's `REPLY_KEY` (from the kept env file) after the current key, restart,
  and run `admin.sh rotate_reply_key` (section 7).
- Practise a restore at least once a quarter, and once as part of P7
  acceptance. [CONFIRM: drill frequency, Operations]

## 7. Rotate secrets

Every value lives in `/etc/abz-chatbot/env` and is read when the service
starts: edit with `sudoedit /etc/abz-chatbot/env`, then
`systemctl restart abz-chatbot`. The next nightly backup carries the new file.

| Secret | How | Effect |
|---|---|---|
| `ADMIN_PASSWORD` | New value, restart. | Staff sign in again. |
| `REPLY_KEY` | See below. | None, if the steps are followed in order. |
| `USER_KEY_SECRET` | Only if it leaks. New value (`openssl rand -hex 32`), restart, note the date. | Reports count returning customers as new from that date. Open sessions keep their old hash until they expire. |
| `WA_ACCESS_TOKEN`, `MS_PAGE_TOKEN` | Generate a new token in Meta Business Settings, restart, then revoke the old one. | None. |
| `WA_APP_SECRET`, `MS_APP_SECRET` | Reset the app secret in the Meta app, then update the env file and restart at once. | Webhooks fail signature checks (401) until the restart; Meta redelivers them. [VERIFY: Meta's redelivery window] |
| `WA_VERIFY_TOKEN`, `MS_VERIFY_TOKEN` | New value, restart, then re-verify the webhook in the Meta app. | Used only when subscribing. |
| `JIRA_API_TOKEN` | Create a new token for the Jira account, restart, revoke the old one. | None. |
| TLS certificate | Let's Encrypt renews itself (certbot timer). A bank certificate: replace the files, `nginx -t && systemctl reload nginx`. | None. |
| Backup `age` key | New key pair; put the new public key in `backup.conf`. Keep the old private key until every archive made with it has expired, here and off the VM. | None. |
| Deploy and backup SSH keys | New key, install it at the other end, remove the old one. | None. |

**Rotate `REPLY_KEY`** (sealed WhatsApp and Messenger reply addresses; a lost
key makes every stored one unreadable). The variable takes several keys,
comma-separated: the first seals, all of them unseal.

1. `sudo /opt/abz-chatbot/current/deploy/admin.sh rotate_reply_key --generate` prints a new key.
2. Set `REPLY_KEY=<new>,<old>` and restart.
3. `sudo .../admin.sh rotate_reply_key` re-seals every stored value with the
   new key. It is safe while the service runs; it prints counts, never values.
4. `sudo .../admin.sh rotate_reply_key --check` must report 0 on an old key.
   If rows changed while step 3 ran, run step 3 again.
5. Set `REPLY_KEY=<new>` and restart.

## 8. Environment variables

`deploy/env.example` lists every variable the app reads, and a test fails if
one is missing. Kill switches belong in `flags.json`, not here: a value in the
env file overrides `flags.json` and needs a restart to change.

| Variable | Required | What |
|---|---|---|
| `ABZ_DATA_DIR` | yes | Databases and generated files. `/var/lib/abz-chatbot/data` |
| `ABZ_FLAGS_FILE` | yes | Kill switches. `/etc/abz-chatbot/flags.json` |
| `EMBED_MODEL_DIR` | yes | The embedding model. `/opt/abz-chatbot/models/all-MiniLM-L6-v2` |
| `PROXY_HOPS` | yes | 1 with nginx alone; 2 if a bank load balancer or WAF is also in front. |
| `ALLOWED_ORIGINS` | yes | The website(s) embedding the widget, comma-separated. |
| `USER_KEY_SECRET` | yes | HMAC secret for `user_hash`. |
| `REPLY_KEY` | yes | Fernet key(s) for sealed reply addresses, primary first. |
| `ADMIN_USER`, `ADMIN_PASSWORD` | for staff pages | `/admin/*` is 404 while either is unset. |
| `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID` | for WhatsApp | Mock mode while unset. |
| `WA_APP_SECRET`, `WA_VERIFY_TOKEN` | for WhatsApp | Webhook signature and subscription check. |
| `WA_GRAPH_VERSION` | no | Default `v23.0`. [VERIFY: current version before launch] |
| `GRAPH_BASE_URL` | no | Leave unset (`https://graph.facebook.com`). |
| `MS_PAGE_TOKEN`, `MS_PAGE_ID`, `MS_APP_ID` | for Messenger | Mock mode while the token is unset. |
| `MS_APP_SECRET`, `MS_VERIFY_TOKEN` | for Messenger | Webhook signature and subscription check. |
| `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` | for real Jira | Mock mode until all four are set. |
| `JIRA_MOCK_PROJECT_KEY` | no | Mock-mode key prefix, default `CC`. |
| `CHATWOOT_URL` | with H2 | Agent desk; WhatsApp handoff then defaults to "inbox". Other `CHATWOOT_*` arrive with H2. |
| `HANDOFF_MODE_WEB`, `_WHATSAPP`, `_MESSENGER` | no | `callback` or `inbox` per channel. |
| `ALERT_WEBHOOK_URL` | with R1 | Where `admin.alerts` posts. |
| `FREE_TEXT_ENABLED`, `WIDGET_ENABLED`, `WHATSAPP_ENABLED`, `MESSENGER_ENABLED`, `MESSENGER_PUBLIC_REPLIES`, `JIRA_ENABLED`, `EMBEDDINGS_ENABLED`, `SHADOW_MATCHER`, `URGENT_MODEL_ENABLED` | no | Kill switches: keep them in `flags.json`. |
| `EMB_HIGH`, `EMB_MEDIUM`, `EMB_URGENT` | no | Thresholds from calibration; leave unset. |
| `IDLE_REGREET_MINUTES`, `FLOW_EXPIRY_HOURS`, `FLOW_EXPIRY_HOURS_URGENT`, `STALE_MESSAGE_MINUTES` | no | Session timings (defaults 30 min, 24 h, 72 h, 10 min). |
| `TRANSCRIPT_RETENTION_DAYS`, `TICKET_RETENTION_DAYS` | no | Defaults 90 and 0 (never). [CONFIRM: Legal] Keep `logrotate.conf`'s 90 days in step. |
| `RATE_LIMIT_PER_MINUTE`, `USER_RATE_LIMIT_PER_MINUTE` | no | Defaults 20 per IP and 20 per customer. |
| `SESSION_STORE` | no | Leave unset (SQLite); `memory` is for tests. |
| `ABZ_EMERGENCY_PHONE`, `ABZ_CONTACT_PHONE`, `ABZ_CONTACT_EMAIL`, `ABZ_WEBSITE_URL`, `ABZ_TARIFF_URL`, `PUBLIC_HOLIDAYS` | no | Contact details and holidays shown to customers; defaults in `app/config.py`, several still `[CONFIRM`. |

## 9. Day to day

- **Logs:** `journalctl -u abz-chatbot` (the app), nginx's
  `/var/log/nginx/abz-chatbot.*.log` (kept 14 days, no query strings),
  `/var/log/abz-chatbot/` (deploys, tests, backups).
- **Admin commands** run with the service's environment through
  `deploy/admin.sh`, e.g. `sudo /opt/abz-chatbot/current/deploy/admin.sh report --days 7`.
- **Latency and memory:** `GET /admin/timing` (staff only) gives the server's
  own p50/p95/p99 per route and per webhook message, the inbox queue and RSS
  (P9, `docs/load-test-results.md`).
- **Kill switches:** `sudoedit /etc/abz-chatbot/flags.json`; no restart
  needed. The incident runbook (R1) lists which switch does what.

## 10. P7 acceptance on the VM

- [ ] Two deploys of different tags.
- [ ] Two rollbacks, one of them to a named tag.
- [ ] One restore from an off-VM copy, with the key from its custodian.
- [ ] `/health` green from outside the bank's network, on the uptime checker.
- [ ] A nightly backup has arrived at the off-VM destination.
- [ ] `systemd-analyze security abz-chatbot` score recorded.
- [ ] The P9 load test run against the VM (`docs/load-test-results.md`).
