---
name: stage-explorer
description: Study a live website and write its Stage Spec (moves, spoken labels, kits, claims) so the voice agent can drive it; read what a hosted site already knows through the Voqalize sites MCP tools. Use when onboarding a site we do not control to Stage, or when a site's moves or labels no longer match the live page.
---

# Exploring a site for Stage

The output is a Stage Spec for the site (`scene.json`) that `voqalize stage check` passes,
and the evidence for every move: the page it works on and what the visitor sees there.
Our servers never fetch from a customer's site; you read it in a browser, and any live read
the agent needs at call time runs on the page.

## 1. Read what is already known

For a site already onboarded as a hosted site, read its knowledge before crawling:

- `list_sites(tenant)` → the site's `id`, its published and latest versions.
- `get_site_version(tenant, site_id, version)` → its topics, parts and tools.
- `read_site_knowledge(tenant, site_id, part, version?)` with `l1` (the brief),
  `l2:<topic>`, and, for the tenant's owner or admin only, `page_map` (the pages and
  listings) and `questions`. Long parts come in pages: pass `next_cursor` back as `cursor`.

The page map and the tools say which pages matter and what the site can do today. Change
knowledge only through `start_knowledge_edit` → `edit_knowledge` → `check_knowledge_edit` →
`submit_knowledge_edit`, never by hand; a submitted version is reviewed and published by a
person.

Publishing a Stage Spec inside a hosted site's pack is not built yet (it waits for the next
pack format): until then the spec lives beside the site's own brain or extension, as
`demos/<site>/scene.json` does.

## 2. Walk the site as a visitor would

For each page type a visitor reaches in a good visit (home, a listing, an item, a booking or
contact flow), note:

- **Regions** the agent should point at, each by the heading the visitor sees, in every
  language the site serves. These become the labels a `{show: …}` cue names.
- **Controls** that change the page (filters, sort, tabs, a calendar) and what they accept:
  the option labels as the page writes them.
- **What the person owns** (cart, forms, bookings): these are `confirmed` moves, or not
  moves at all when they mean paying, consent or personal data.
- **How the site loads** (full page loads, a second origin for booking, client routing):
  it decides `navigate` moves and how a move carries across a load.

## 3. Write the spec

Take kits before writing moves (`commerce` for a store). Write each remaining move with the
`stage-move` skill. Give every move that changes the page `claims` and `objects` in each
language the site speaks.

```sh
uv run voqalize stage check <site>/scene.json --strict
```

## 4. Prove each move on the live page

Run the site's extension against dev and make each move in a call, or with the page test
kit (`@voqalize/stage/conformance`) on a saved copy of the page. A move is proven when it
rings its target, acts, and reports `applied` with a detail the model can repeat; a label
that matched nothing comes back `refused` with what the page offers, which is the label to
fix.

## Never

- Invent a label, a heading or an option: copy it from the page.
- Write selectors, waits or click orders into the spec: those belong to performers.
- Let a move pay, submit personal data, tick consent or solve a captcha.
