---
title: Site Agent settings
description: The assistant's name and greeting, its avatar and languages, the button's look, where and when it shows, how visitors reach a person, and what the assistant may do. Every key, its default, and how a change goes live.
---

Settings belong to the site, not to a version: a save is live on the next
page load, with no new version and no review. No study, and not the quick first
read, overwrites a look a person saved.

An owner or admin changes them in the console or with
`update_site_settings` over [MCP](/reference/mcp/#site-agent-tools).

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
| `greeting` | none | The assistant's first words; at most 160 characters. A page can override it ([tag options](/build/site-agent/install/#options-on-the-tag)). |
| `avatar.enabled` | `true` | Whether the call shows an animated character. |
| `avatar.character` | `tara` | Which character; the [catalog](/reference/catalog/) lists them. |
| `voice.languages` | `["english"]` | The languages the assistant speaks, as names. |
| `voice.default_language` | `english` | The one calls start in; one of `voice.languages`. |
| `colours.accent`, `.background`, `.text` | derived | The button's colours, each `#rrggbb`. |
| `position` | `bottom-right` | `bottom-right` or `bottom-left`. |
| `show_on.include` | `["/**"]` | Path globs where the button shows. |
| `show_on.exclude` | `[]` | Path globs where it never shows; these always win. |
| `hours` | none (always) | `{timezone, weekly: [{day, open, close}]}`, `day` `mon` to `sun`, times `HH:MM`. Outside them the button is hidden. `timezone` defaults to `Asia/Kolkata`. |
| `human_contact` | from the study | `{phone, email, whatsapp, url}`: how the assistant tells a visitor to reach a person. |
| `assist` | all on | What the assistant may do; below. |

A site's first full study chooses `assistant_name`, `greeting`, `colours` and
`position` for you, unless a person has already saved them; no later study
changes them.

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

## In the console only

- **Goals:** what the assistant leads visitors towards. A patch over MCP never
  changes them.
- **Notes:** corrections or additions to what the assistant knows, typed
  during review; at most 50 notes of at most 300 characters each. A note that
  states a price, stock or reviews is refused; those are read from the page.
- **The robots notice:** turning off the reader's permission to read pages
  `robots.txt` asks crawlers to skip.
