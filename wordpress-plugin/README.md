# AB Bank Chatbot — WordPress plugin

Drops the chat widget onto every page via WordPress's own settings screen — no
theme edits, no FTP, no touching PHP by hand. Works because `widget/widget.js`
already supports loading from a different domain than the one it's embedded
on (`data-endpoint` attribute) — the plugin just outputs that script tag.

## Install

The plugin is a single file, `ab-bank-chatbot.php` — no folder, no build
step. Two ways to install it, in order of preference:

**A. File manager / FTP (most reliable, use if available)**
If whoever manages the site has access to a hosting file manager (cPanel,
Plesk, etc.) or FTP, just copy `ab-bank-chatbot.php` directly into
`wp-content/plugins/` on the server, then activate it from **Plugins** in
WP admin. This skips zip upload and extraction entirely, which removes an
entire category of possible failure (see Troubleshooting below).

**B. Upload via WP admin (if no file-manager access)**
1. Zip just `ab-bank-chatbot.php` (or use `ab-bank-chatbot.zip` alongside
   this file — it already contains only that one file at the top level).
2. WordPress admin → **Plugins → Add New → Upload Plugin** → choose the
   zip → **Install** → **Activate**.

**Then, either way:**
3. **Settings → AB Bank Chatbot** → paste the backend URL (e.g. the Render
   URL from `../docs/deployment-and-jira-setup.md`) → **Save**.
4. The widget now appears bottom-right on every page. It stays invisible if
   the backend's `WIDGET_ENABLED` kill switch is off or the backend is
   unreachable — safe to install ahead of the backend being ready.

## Troubleshooting: "Plugin file does not exist" on activate

This happened once already with the folder+zip version of this plugin
(fixed by flattening it to a single file, above — a zip built on Windows
had stored the internal path with a backslash instead of a forward slash,
which Linux-hosted WordPress didn't parse as a folder separator). If it
happens again with the new single-file zip, it's likely one of these
instead, roughly in order of likelihood on shared hosting:

- **A leftover from the previous failed attempt.** Delete the
  "AB Bank Chatbot" row from the Plugins list (even if it shows an error)
  before re-uploading, so there's no stale/partial file to conflict with.
- **A host security scanner quarantined or deleted the file** between
  install and activate. Some shared-hosting malware scanners flag any
  plugin that outputs a `<script src="...">` tag built from a stored
  option as suspicious (it resembles a common backdoor pattern), and
  silently remove it right after extraction. If a file manager or FTP is
  available, check `wp-content/plugins/` right after a failed activation —
  if `ab-bank-chatbot.php` isn't there at all, this is what happened, and
  the host's security/support team (not necessarily "IT" in the
  bank-internal sense) would need to whitelist it.
- **ZipArchive isn't available on the server**, so WordPress falls back to
  a slower, older unzip method (PclZip) that has historically had its own
  edge-case bugs with certain archive structures. The single-file zip
  (no subfolder) avoids the archive structures most likely to trip this.

If in doubt, option A above (dropping the raw `.php` file in via file
manager/FTP) sidesteps all three of these at once.

## WordPress.com vs. self-hosted (confirmed 2026-07-22)

## WordPress.com vs. self-hosted (confirmed 2026-07-22)

Confirmed: this site is **self-hosted WordPress (wordpress.org)**, not
WordPress.com. No plan-tier restriction applies — custom plugin uploads work
out of the box, so this plugin can be installed directly by anyone with
`Plugins → Add New → Upload Plugin` access (marketing, most likely — no IT
involvement needed for this step).

## Also required: CORS on the backend

The widget calls the backend from the WordPress domain, which is a different
origin. The backend's `ALLOWED_ORIGINS` environment variable must include the
WordPress site's URL (e.g. `https://abbank.co.zm`) or the browser will block
every chat request with a CORS error, even though the widget itself loads
fine. See `../README.md` → "Deployment notes for IT".
