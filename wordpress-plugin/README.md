# AB Bank Chatbot — WordPress plugin

Drops the chat widget onto every page via WordPress's own settings screen — no
theme edits, no FTP, no touching PHP by hand. Works because `widget/widget.js`
already supports loading from a different domain than the one it's embedded
on (`data-endpoint` attribute) — the plugin just outputs that script tag.

## Install

1. Zip the `ab-bank-chatbot/` folder (or use `ab-bank-chatbot.zip` if one is
   provided alongside this file).
2. WordPress admin → **Plugins → Add New → Upload Plugin** → choose the zip → **Install** → **Activate**.
3. **Settings → AB Bank Chatbot** → paste the backend URL (e.g. the Render
   demo URL, or the production server once IT stands one up) → **Save**.
4. The widget now appears bottom-right on every page. It stays invisible if
   the backend's `WIDGET_ENABLED` kill switch is off or the backend is
   unreachable — safe to install ahead of the backend being ready.

## The WordPress.com catch

Custom plugin installs (this one included) are **only available on
WordPress.com's Business plan or higher** — Free/Personal/Premium plans block
uploading your own plugins entirely. Self-hosted WordPress (wordpress.org,
your own hosting) has no such restriction. **Confirm which kind of WordPress
this actually is, and the plan tier if it's WordPress.com, before assuming
this plugin can be used.**

If it turns out to be a restricted WordPress.com tier, the fallback is
whatever WordPress.com's own embed mechanism allows on that plan — typically
none for arbitrary `<script>` tags below Business. In that case the realistic
options are: ask marketing to upgrade the plan, ask if the site is actually
self-hosted behind a WordPress.com facade (common with agency-built sites),
or revisit whether the widget belongs on the site directly vs. WhatsApp/USSD
(see the "Zambian context" section of the main project notes for why that
channel priority already made sense independent of this).

## Also required: CORS on the backend

The widget calls the backend from the WordPress domain, which is a different
origin. The backend's `ALLOWED_ORIGINS` environment variable must include the
WordPress site's URL (e.g. `https://abbank.co.zm`) or the browser will block
every chat request with a CORS error, even though the widget itself loads
fine. See `../README.md` → "Deployment notes for IT".
