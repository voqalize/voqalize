---
title: Install the Site Agent snippet
description: The one script tag, its per-page options, the Content-Security-Policy sources it needs, letting the site reader past bot protection, trying a site before installing, and exactly what a call sends.
---

The Site Agent runs from one script, the same for every website. Only the key
in it is yours.

## The tag

Paste it just before `</body>` on every page where the assistant may appear,
with your site's key in place of `pk_live_…`:

```html
<script async src="https://cdn.voqalize.com/sites/site.js" data-key="pk_live_…"></script>
```

- **The key is shown once.** `create_site` and the console's Add a site return
  the snippet with the key in it, and it cannot be read again. The console then
  lists only its prefix.
- **Lost it? Rotate it.** The console's **Rotate key** makes a new key and a
  new snippet; the previous key keeps working for 24 hours while you update
  your pages.
- **It works only on the site's own origins**, so it need not be kept secret.
- **The URL never changes.** A new published version needs no change on your
  pages.
- **Paste it early if you like.** Until a version is published the script shows
  nothing.

Where the button shows, its hours, corner and colours are
[settings](/build/site-agent/settings/), not tag attributes.

## Options on the tag

| Attribute | Does |
|---|---|
| `data-language="hindi"` | The language a call on this page starts in, as a language name, not a code. It must be one of the site's languages, in any case; any other value is ignored. |
| `data-greeting="…"` | The assistant's first words on this page. Plain text of at most 280 characters; tags and invisible characters are removed, and a longer value is ignored. |
| `data-hide="1"` | Hide the button on this page. `true`, `yes` and an empty value also count. |

## Options from your page's code

A page your site builds without a full reload can set the same options in
script, before or after `site.js` loads:

```html
<script>
  window.VoqalizeSite = { greeting: "Looking for a gift? I can help.", language: "english" };
  // after site.js has loaded:
  // window.VoqalizeSite.configure({ hide: true });
</script>
```

The keys are `hide`, `greeting`, `language` and `pageType`. `pageType` names
one of the site's page types (letters, digits, `_` and `-`) when the address
alone does not say which kind of page this is. A value set in code beats the
tag, a later value beats an earlier one, and an invalid value falls through to
the tag and then to the site's settings. Reassigning `window.VoqalizeSite` and
calling `configure` both take effect at once.

## Where the button shows

The button shows where the site's `show_on` setting allows and inside its
`hours`. On top of that:

- **Your visitors' own pages** (account, orders, addresses and the like): the
  button shows unless `assist.account_pages` is off. The assistant reads
  nothing there and can only point at a section and help the visitor leave.
- **Cart, checkout and payment pages:** the button shows unless
  `assist.cart_pages` is off. The assistant only looks; on the cart page it
  reads the cart's lines.
- **Pages that change state by being opened** (sign-out, account deletion,
  emptying the cart): never.

Your own `show_on` exclusions always win.

## If your site sets a Content-Security-Policy

If your site sends a `Content-Security-Policy`, add these sources:

```text
script-src   https://cdn.voqalize.com https://avatar.voqalize.com
connect-src  https://app.voqalize.com https://*.prod.voqalize.com https://avatar.voqalize.com blob:
img-src      https://avatar.voqalize.com blob:
media-src    blob:
```

- `cdn.voqalize.com` serves `site.js` and the call code it loads on the first
  click.
- `avatar.voqalize.com` serves the avatar and its pictures.
- `app.voqalize.com` is the API: the script reads the site's settings from it
  and starts calls through it.
- `*.prod.voqalize.com` is where a call's voice connection is set up; the
  server is chosen when the call starts, so it is a wildcard.
- `blob:` is how the browser plays the voice and decodes the avatar's frames.

No `style-src` change is needed: the button adds its styles to its own shadow
root as a constructed stylesheet, which `style-src` does not block. A browser
without constructed stylesheets (Safari before 16.4) gets a `<style>` element
instead; to style the button there under a strict `style-src`, add
`'unsafe-inline'`. The voice travels over WebRTC, which a Content-Security-Policy
does not govern.

## If your site blocks automated visitors

Voqalize reads your public pages when a study runs. Bot protection such as
Cloudflare or Akamai may block the reader; the study's version is then
`blocked` and the console says so. The reader sends this user agent:

```text
Mozilla/5.0 (compatible; VoqalizeSiteReader/1.0; +https://voqalize.com/site-reader)
```

Allow requests whose user agent contains `VoqalizeSiteReader/1.0`, then run the
study again.

- **Cloudflare:** add a WAF custom rule where *User Agent* contains
  `VoqalizeSiteReader/1.0`, with the action **Skip** for the features that
  blocked it.
- **Akamai:** add a Bot Manager custom bot definition matching that user agent,
  with the action **Allow**.

An IP allowlist will not work: the reader's addresses change between runs and
are not published.

The reader never signs in, submits a form or buys anything.

### robots.txt

Adding a site asks the person to agree to this notice:

> Adding your site lets Voqalize read all its public pages, including ones
> robots.txt asks crawlers to skip. You can turn this off in Settings.

With that agreement the reader may read pages your `robots.txt` asks crawlers
to skip. Without it, or once it is turned off in Settings, studies obey
`robots.txt`, and the reader matches `robots.txt` groups by its product token,
`VoqalizeSiteReader`. Only a tenant owner or admin can agree.
Over MCP, `create_site` takes the agreement as `robots_acknowledgement_version`;
the current wording's version is `2026-10-15-default`.

## Try it before you install

A preview invite lets someone try a version on your live site, in their own
Chrome, before the snippet is on any page and before the version is published.
There is no sign-in.

- **Share a preview.** An owner or admin creates a client invite in the console
  or with `create_site_invite`: a label saying who it is for, how many days it
  works and how many voice minutes it may use. The link, `…/p/<code>`, is shown
  once. The site must have a version to preview.
- **Preview it yourself.** Any member can use **Preview in my browser** in the
  console. That member invite lasts 30 days and has no minute budget.
- **Opening the link** shows how to install the Voqalize Preview extension,
  then opens the site. The extension is downloaded from the console and
  loaded unpacked (`chrome://extensions`, **Developer mode**, **Load
  unpacked**). It asks Chrome for access to the site's own origins only.
- **On the page** the button carries a **Voqalize Preview** badge and follows
  the same rules as the installed snippet. A page that already runs the snippet
  is left alone.

Voice minutes are checked when a call starts; a call that crosses the budget is
not cut. Revoking an invite also revokes every key made from it, so the next call
from that browser is refused. Each person's key lasts 24 hours and is refreshed from the invite
until the invite ends.

## What is sent

### When Voqalize reads your site

- Public pages only, over the reader above.
- No personal data goes into the knowledge. Reviews and comments your
  customers wrote are left out.

### When a visitor starts a call

The call's start carries the site, the published version, the page's path with
no query string, the page type, whether it is a preview, and the page's own
language and greeting if it set them. No name, email, account or cookie. The
visitor's voice goes to Voqalize so the assistant can hear it.

### During the call

The assistant follows the page so it can talk about what the visitor sees:

- which page the visitor is on, and its type;
- a short outline of the page: headings, numbered cards and capped text, with
  words searched for in the address masked;
- on an item or listing page, the fields the reviewed version declares, such as
  name, price, options and stock;
- the text of an open dialog, cut short if long;
- on the cart page, the cart's lines: name, quantity and price;
- when the visitor starts speaking, which outline sections and cards are in
  view, what kind of field has focus, and what they just did.

It never receives what a visitor typed into the page. After a form fill it
learns which fields were filled, not their values; after a search, the query's
length. On a visitor's own pages it learns only that the page is private: no
title, no text, and the path cut at the private segment.

### What the assistant can do on the page

It can open pages, search, sort and filter, show a section, open and close a
dialog, choose an option, and point at things. With the site's `assist`
switches on (the default), and only through site tools a check has proven, it
can also add to the cart, change or remove a cart line, apply a code the
visitor says, switch language, region or currency, type into the site's search
box, and fill a form or a booking up to its final step. A form is sent only
after the visitor has heard its fields read back and said yes. It never
presses payment, checkout or sign-out controls and never places an order.
These limits are enforced by the script on the page, not left to the
assistant's judgment.

Each call is a session in your tenant, kept for 30 days like any other.
