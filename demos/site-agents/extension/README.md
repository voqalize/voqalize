# Javier on a Site Agent — the extension template

A Chrome extension that puts Javier, a voice guide, on a customer's own site,
talking to that site's **live Site Agent**: the published agent the paste-in
snippet would run, on the platform's shared Site Agent brain, with the
experience of our hand-built demos (agroplanet, qween): the corner widget with
his face and an Español/English toggle in the site's colours, a ring around
what he points at, and one call that lives through every full page load and
across the site's tabs.

The first site is [WOM](https://www.wom.cl) (`sites/wom/site.ts`). A new site
is one file.

This is how we show a Site Agent to a customer on their own site before the
snippet goes on it; it is not how a customer ships it.

## How it is put together

The extension is the shared Stage extension host (`@voqalize/stage/extension`,
the same as `demos/agroplanet/extension/`) with the Site Agent snippet's own
page parts inside it:

| Part | Whose | What it does |
|---|---|---|
| `src/background.ts` | shared host | makes the holder, opens and focuses tabs (only at the site's `openable` addresses), keeps moves across loads and the language choice |
| `src/holder.ts`, `call.html`, `call-client.ts` | shared host | the call, in an offscreen document: pipecat on `@voqalize/client-transport`, his voice, Stage's timeline |
| `src/shell.ts` | shared host | in a call, the widget back at once on the next page |
| `src/bridge.ts`, `src/grant.ts`, `grant.html` | shared host | the page ↔ extension messages; the one-time microphone grant |
| `src/content.ts` | this template | the widget, his face (`createAvatar({character: "javier"})`), and the Site Agent adapter |
| `src/agent.ts` | this template | `embed.config` with the site's key, the session's `init` |
| `src/adapter.ts` | snippet parts | the snippet's watcher, executor, Stage moves and note cards on the host's page kit |
| `src/site.ts` | this template | Javier, ES/EN, every word in Spanish (Chile) and English |
| `sites/<id>/site.ts` | the site | origin, colours, ring, corner, what to keep clear of, `openable`, manifest key |

What the Site Agent's brain speaks that a demo brain does not, and where it is
handled:

- **`stage_hello`.** The Site Agent's brain sends no cues to a page that has
  not said hello; the shared holder never sends one. Every page says it once
  the brain hears it, and again when its tab comes back to the front
  (`adapter.ts`, `report`).
- **Its only two Stage moves**, `site.page {page}` and `site.show {region}`
  (a region id, a digest heading `d:<seq>:s<n>`, a card `c:<seq>:<n>`, a goal
  `g:<id>`), are the snippet's own performers, registered on the host's
  `Moves`. `build.mjs` exports them from the snippet's `call/stage.ts` as it
  bundles, so they run as written there.
- **Its Actions** (`run_site_tool`, `read_site`, `open_page`, `open_item`,
  `open_listing`) go to the tab in front and through the snippet's executor,
  answered with the snippet's own result events; `show_note` is a note card
  above the widget; `language_set` moves the toggle on every tab (`holder.ts`).
- **What the page reports** is the snippet's watcher: `page_viewed` with the
  digest, `tools_available`, `item_viewed`, `listing_viewed`, `cart_viewed`,
  dialogs, and `screen_seen` once per utterance. The call's ledgers (page
  count, tool failures, coupons, undoable runs) are shared by the site's tabs
  under the call's id (`call-store.ts`).
- **`init`** is the snippet's: `{site_id, version, path, page_type, preview}`
  and `language` (not `lang`) when the call opens in one the site serves. The
  agent, the site and the version come from `embed.config`.
- **The toggle** sends `set_language {language}` as a client message, the
  way the snippet's language chips do, and moves only on the brain's
  `language_set`. A language the site's settings do not serve is not asked
  for at the start, and a switch the brain does not confirm falls back on the
  toggle after 4 s.

Javier, his name and the two languages are the extension's, whatever the Site
Agent's settings name. The call opens in Spanish when the site serves it, else
in the site's default (which is what the brain would open in anyway), and the
toggle says which.

## Build and load

You need a checkout of the platform repository: the snippet's source is
bundled from it. `scripts/link-platform.mjs` links it as `.platform/`
(gitignored); it finds a `platform/` checkout beside a parent directory of this
one, or set `VOQALIZE_PLATFORM_DIR`.

```sh
cd demos/site-agents/extension
cp .env.example .env            # the site's publishable key (never committed)
pnpm install --ignore-workspace
pnpm typecheck
node build.mjs --site wom       # → dist/wom/   (pnpm build does typecheck + this)
node build.mjs --all            # every sites/*/site.ts → dist/<id>/
```

Load `dist/wom/` unpacked in `chrome://extensions` (Developer mode → Load
unpacked). Open https://www.wom.cl and press *Habla con Javier*; the first
time, Chrome asks for the microphone for the extension.

**The key.** `VOQALIZE_PUBLISHABLE_KEY` is the site's own live publishable key
(`pk_live_…`, the site key the owner rotates in the console). It is baked into
`content.js` and used from the page's own world, so `embed.config` and
`sessions.connect` carry the site's Origin, which the key is allowed on. For
several sites, put one `sites/<id>/.env` per site; it is read before the
shared `.env`. `VOQALIZE_API_BASE` defaults to production. A build without a
key succeeds with a warning, and the widget says the call cannot start.
`VOQALIZE_AGENT_ID` is optional: a cross-check against what `embed.config`
serves, logged when they differ.

**The extension id is fixed** for each site: its `site.ts` carries a manifest
`key` (an RSA public key; not a secret), so the unpacked extension has the
same id from any folder and machine, and the microphone grant holds across
rebuilds. WOM's is `jdpnhnchiacekmhpocipljafkmgedclm`. The private key is not
in the repo; it is only needed to pack a `.crx`.

## Adding a site

1. **The Site Agent first.** The site must have a published Site Agent and a
   live publishable key whose allowed origins include the site's origin.
2. **Read the site.** `curl -sI https://<site>/` for its headers: a
   `Content-Security-Policy` with `script-src`, `connect-src` or `frame-src`
   would block the avatar runtime, our API or the grant frame, and needs a
   `declarativeNetRequest` header rule as `demos/cannonhome/extension` has
   (WOM sends only `frame-ancestors`, which needs none). Draw the home page
   and note its palette, face, fixed header, and what it pins in the corners
   (chat, WhatsApp, reCAPTCHA, cookie bar, accessibility menu).
3. **Copy `sites/wom/site.ts` to `sites/<id>/site.ts`** and fill it in:
   `id`, `siteName`, `origin`, `matches`, `openable` (its own pages, never
   login, account or payment flows), the widget `corner` and `topClear`, the
   `fixed` header, the `obstacles`, the `theme` read off the site, a `ring`
   colour that holds on the site's backgrounds and is none of its buttons
   (with the contrast written down), `grantStyle`, `dismissOnCall` for an
   offer pop-up if it has one, and a `description`.
4. **A manifest key of its own:**

   ```sh
   openssl genrsa -out <id>.pem 2048       # keep it out of the repo
   openssl rsa -in <id>.pem -pubout -outform DER | base64 | tr -d '\n'   # → manifestKey
   openssl rsa -in <id>.pem -pubout -outform DER | shasum -a 256 | cut -c1-32 | tr '0-9a-f' 'a-p'   # → extensionId
   ```

5. **Its key** in `sites/<id>/.env`, then `node build.mjs --site <id>` and
   `pnpm typecheck` (which checks every site file against `SiteAgentSite`).
6. **Check it live** (below), then on the site with a real call.

The site's pages, regions, tools and navigation are not in its file: they are
the Site Agent's adapter, served by `embed.config`.

## Checking it on the live site

```sh
node build.mjs --site wom --out dist/wom-verify      # any key; a made-up one is fine
CHROMIUM=".../Google Chrome for Testing" node test/verify-live.mjs dist/wom-verify https://www.wom.cl/ /prepago/
```

Loads the built extension in headless Chromium on the site and checks the
widget and its still, the `embed.config` request (Origin, Bearer key, no
cookies), CSP violations and the extension's console errors, the console
handle's two moves, and that the early shell puts the widget back before the
next page's scripts run on a full page load mid-call. Screenshots land in
`test-results/`. A real call needs the real key and a microphone.

## Driving it from the console

With the real key, on a WOM page:

```js
__voqalizeWOM.moves();                                       // ["site.page", "site.show"]
await __voqalizeWOM.move("site.page", { page: "<page id>" }); // a page of the adapter's page map
await __voqalizeWOM.move("site.show", { region: "<region id>" });
```

## WOM, as read on 2026-11-03

- Headers: `Content-Security-Policy: frame-ancestors 'self'` and
  `X-Frame-Options: SAMEORIGIN` only; no header rule needed.
- Bottom-right widget: WOM's accessibility menu owns the bottom-left;
  "Contrata Ahora" sits mid-right; reCAPTCHA's badge and the cookie bar are
  kept clear of. The offer pop-up (`#popupPlanes`) is closed with its own ×
  when a call starts; the cookie bar is the visitor's to answer.
- Plans (`/planes/`), phones and accessories live on **store.wom.cl**, a
  different host, and MiWOM on miwom.wom.cl: the extension runs on
  www.wom.cl and wom.cl only, and the snippet's executor opens only
  same-origin addresses, so a page map entry there is refused, not opened.
