---
title: Site Agent settings
description: The assistant's name and greeting, its avatar, languages and per-language instructions, the button's look, where and when it shows, per-page options on the tag, how visitors reach a person, what the assistant may do, and pausing. Every key, its default, and how a change goes live.
---

Everything so far changed what the assistant knows, through versions. How it
looks and behaves on your pages is set separately, in the site's **settings**,
which the first studied publish filled in for you
([The Site Agent](/build/site-agent/#review-and-publish-the-first-version)).

Settings belong to the site, not to a version: a save is live on the next
page load, with no new version and no review. An owner or admin changes them
in the console or with `update_site_settings` over
[MCP](/reference/mcp/#site-agent-tools).

## Change settings over MCP

`update_site_settings(tenant, site_id, settings, expected_updated_at="")`.

- **`settings` is a JSON merge patch** over `site.settings` as `get_site` shows
  it. Name only what changes: an object merges key by key, `null` puts a key
  back to its default, and a list (such as `voice.languages` or
  `assist.tools_off`) is replaced whole.
- **Pass the `site.updated_at` you read** as `expected_updated_at`. If the site
  changed since, nothing is saved and the call is refused with `site_changed`;
  read the site and send the patch again.

## Keys

| Key | Default | Sets |
|---|---|---|
| `assistant_name` | `Assistant` | The name on the button and in the call; at most 40 characters. |
| `greeting` | none | The assistant's first words; at most 160 characters. A page can override it ([tag options](#options-on-the-tag)). |
| `avatar.enabled` | `true` | Whether the call shows an animated character. |
| `avatar.character` | `tara` | Which character; the [catalog](/reference/catalog/) lists them. |
| `voice.languages` | `["english"]` | The languages the assistant speaks, as names. |
| `voice.default_language` | `english` | The one calls start in; one of `voice.languages`. |
| `voice.instructions` | none | Per language, plain text the assistant follows when it speaks that language, such as the currency to say prices in: `{"hindi": "…"}`. Each key one of `voice.languages`; each text at most 500 characters. |
| `colours.accent`, `.background`, `.text` | derived | The button's colours, each `#rrggbb`. |
| `position` | `bottom-right` | `bottom-right` or `bottom-left`. |
| `show_on.include` | `["/**"]` | Path globs where the button shows. |
| `show_on.exclude` | `[]` | Path globs where it never shows; these always win. |
| `hours` | none (always) | `{timezone, weekly: [{day, open, close}]}`, `day` `mon` to `sun`, times `HH:MM`. Outside them the button is hidden. `timezone` defaults to `Asia/Kolkata`. |
| `human_contact` | from the study | `{phone, email, whatsapp, url}`: how the assistant tells a visitor to reach a person. |
| `assist` | all on | What the assistant may do; below. |

The first publish of a studied version sets `assistant_name`, `greeting`,
`colours` and `position` to what the study chose, unless a person has saved
settings by then. Any save counts, of any key, and keeps the study's choices
out of every one of those keys. No later study changes them.

Path globs match the path only, not the query: `**` matches across `/`, `*`
within one segment, `?` one character, and a trailing `/**` also matches the
folder itself.

### The voice follows the character

Each character speaks in its own voice, so the voice is not a setting: it is
set from `avatar.character`, whatever the patch says. With the avatar off the
site keeps the voice it had. A character none of whose voices speaks every
site language is refused.

### What the assistant may do: `assist`

Each switch is on unless turned off.

| Switch | Turns off |
|---|---|
| `forms` | Filling forms the study declared, and sending one after the visitor confirms. |
| `search_box` | Typing into the site's search box. |
| `account_pages` | The button on visitors' own pages, where the assistant only points at a section. |
| `cart_pages` | The button on cart, checkout and payment pages, where the assistant only looks. |
| `cart_edits` | Changing a cart line's quantity or removing it. |
| `coupon` | Applying a code the visitor says. |
| `switchers` | Switching language, region or currency. |
| `bookings` | Filling a booking flow up to its confirm step. |
| `rating` | Saying an item's live rating. |
| `site_tools` | Every site tool. |
| `open_actions` | Site tools that change something on the page reversibly. |

`assist.tools_off` lists site tools turned off one by one.

## Refusals

Nothing is saved when a patch is refused:

| Code | Means |
|---|---|
| `language_unsupported` | A language the assistant cannot speak. |
| `character_language_unsupported` | No voice of that character speaks every site language. |
| `accent_low_contrast` | The accent colour is hidden by the background; the message names one to use. |
| `site_archived` | The site is archived. |
| `site_changed` | The site changed since `expected_updated_at`. |

## Options on the tag

A page can set a few options for itself on the snippet's tag:

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

The button shows where `show_on` allows and inside `hours`. On top of that:

- **Your visitors' own pages** (account, orders, addresses and the like): the
  button shows unless `assist.account_pages` is off. The assistant reads
  nothing there and can only point at a section and help the visitor leave.
- **Cart, checkout and payment pages:** the button shows unless
  `assist.cart_pages` is off. The assistant only looks; on the cart page it
  reads the cart's lines.
- **Pages that change state by being opened** (sign-out, account deletion,
  emptying the cart): never.

Your own `show_on` exclusions always win.

## Pause the assistant

**Pause** in the console turns the site's live key off: the button no longer
shows on your pages and no visitor call starts, while the snippet stays where
it is. [Previews](/build/site-agent/preview/) still work, and studies still
run. **Resume** turns it back on. There is no MCP tool for either.

## In the console only

- **Goals:** what the assistant leads visitors towards. A patch over MCP never
  changes them.
- **Notes:** one-line corrections to what the assistant knows; see
  [Notes in the console](/build/site-agent/knowledge/#notes-in-the-console).
- **The robots agreement:** whether the reader may read pages `robots.txt`
  asks crawlers to skip ([robots.txt](/build/site-agent/security/#robotstxt)).
- **Pause and resume**, above, and renaming the site.
