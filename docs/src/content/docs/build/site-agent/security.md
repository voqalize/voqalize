---
title: Site Agent CSP, bot protection and data
description: What your site must allow for the Site Agent to work, and what crosses when Voqalize reads your site and when a visitor calls. The Content-Security-Policy sources, letting the reader past bot protection, the robots.txt agreement, and exactly what is sent.
---

The earlier pages assumed the snippet loads on your pages and the reader can
reach them ([The Site Agent](/build/site-agent/)). This page covers sites
where one of those needs a change on your side, then lists exactly what is
sent: when Voqalize reads your site, and when a visitor calls.

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

If the quick first read is turned away, by an answer of 401, 403, 429 or 503
from `robots.txt` or the home page, the starter version knows nothing about
the site and only says it is still learning. A server error on `robots.txt`
means nothing on the site is read.

## robots.txt

Adding a site in the console shows this notice, and adding the site is the
agreement:

> Adding your site lets Voqalize read all its public pages, including ones
> robots.txt asks crawlers to skip. You can turn this off in Settings.

With that agreement the reader may read pages your `robots.txt` asks crawlers
to skip. Without it, studies obey `robots.txt`, and the reader matches
`robots.txt` groups by its product token, `VoqalizeSiteReader`.

- **Only a tenant owner or admin can agree.** A site added by anyone else
  obeys `robots.txt` until an owner or admin turns reading on in Settings.
- **Over MCP the agreement is opt-in.** `create_site` takes it as
  `robots_acknowledgement_version`, the version of the wording agreed to; the
  current wording is `2026-10-15-default`. Leave it empty and the site obeys
  `robots.txt`. The answer's `robots_acknowledgement_recorded` says which.
- **An agreement to an older wording counts as none.** Over MCP, an older
  version is refused with `robots_acknowledgement_outdated`.
- **Turning it off and on** is a switch in the console's Settings; there is
  no MCP tool for it. Anyone who may change the site can turn it off; only an
  owner or admin can turn it back on.
- **Turned off while a study runs**, the study's version must be approved by a
  person, even where it would otherwise have published itself
  ([Which refreshes publish themselves](/build/site-agent/refresh/#which-refreshes-publish-themselves)).

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

### What is kept

Each call is a session in your tenant, kept for 30 days like any other: its
events, its transcript and Voqalize's logs. Site Agent calls are not recorded by
default: the site's agents are created with recording off, and the snippet does
not ask for it.
