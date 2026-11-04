---
title: Edit Site Agent knowledge
description: Change what a site's assistant knows and may do yourself. What a version holds, notes in the console, and knowledge edits over MCP with the draft lifecycle, every edit operation, the checks, and how to prove a changed site tool.
---

Every version so far was written by a study
([Refreshes and review](/build/site-agent/refresh/)). When the assistant has
something wrong, or you want it to know or do something the study missed, you
can change it yourself, with a **note** in the
console, which corrects the assistant at once, or with a **knowledge edit**, a
checked draft that becomes a new version.

The site's look, avatar and languages are [settings](/build/site-agent/settings/),
not knowledge.

## What a version holds

A version's knowledge is read part by part with `read_site_knowledge`:

| Part | Holds | Who may read |
|---|---|---|
| `l1` | What the assistant always knows: it is in every call. | Any member |
| `l2` | The menu of deeper topics, each with when to read it. | Any member |
| `l2:<topic>` | One topic in full. | Any member |
| `report` | The study's report. | Any member |
| `facts` | Each fact, with the page it came from and the quote on that page. | Owner or admin |
| `page_map` | The kinds of page on the site and how to reach them. | Owner or admin |
| `questions` | The questions the study tested the knowledge against. | Owner or admin |
| `stage` | The site's Stage moves: what the assistant can show on screen. | Owner or admin |

Beside the knowledge, a version holds its site tools: the actions the
assistant may run on your pages, each with its proof.

## Notes in the console

A **note** is one line of plain text from the business, added in the console by
an owner or admin, optionally aimed at one fact or one part of what the
assistant always knows. It is not a new version. It is merged into what the
assistant always knows, marked as the business's own words with its date, in
the published and the preview version at once, and it is live on the next
call. Every later version carries it too.

- **A site keeps at most 50 notes of at most 300 characters each.**
- **A note may not state a price, stock or reviews.** Those are read live from
  the page during a call, never kept.
- **The next study checks it.** Where a page now says otherwise, that study
  shows the two as a conflict for review.
- **Notes are console-only.** There is no MCP tool for them.

## Knowledge edits

A knowledge edit changes a stored version through a draft: open it, apply
operations, read the checks, prove any changed site tool, submit. The submit
makes a new version that waits for
[review](/build/site-agent/refresh/#review-in-full). Edits run over
[MCP](/reference/mcp/#site-agent-tools), by an owner or admin; nothing a draft
holds reaches visitors.

### Read before you edit

`read_site_knowledge(tenant, site_id, part)` returns one
[part](#what-a-version-holds) a page at a time: 12,000 characters by
default, `limit` from 1,000 to 40,000, and `cursor` for the next page.
`version` defaults to the published version, else the newest.

### The draft lifecycle

- **`start_knowledge_edit(tenant, site_id, base_version=None)`** opens a draft
  from a stored version, the published one by default. A `starter` version
  cannot be edited: run a study first. A site has one open draft; a second is
  refused with `draft_exists`, naming it. The answer has the `draft` (its
  `revision` starts at 0), its first `check`, and `kit`, a signed link to the
  study kit.
- **`edit_knowledge(tenant, site_id, ops, expected_revision)`** applies a list
  of operations in order, all or none, and returns the draft and its checks.
  `expected_revision` is the `revision` you last saw; another edit since is
  refused with `draft_changed`. A draft that fails its checks is still saved:
  the errors are the answer.
- **`check_knowledge_edit(tenant, site_id)`** returns the draft and runs its
  checks again.
- **`submit_knowledge_edit(tenant, site_id, owner_tested=False)`** turns the
  draft into version `latest + 1` with `origin` `knowledge_edit`, makes it the
  site's preview, and closes the draft. It is never published on its own.
- **`discard_knowledge_edit(tenant, site_id)`** throws the draft away. Stored
  versions are untouched.

A draft expires 7 days after it was started, and an expired draft is gone.

### Operations

Each operation is an object with an `op`. At most 50 per call; an edit that
would make the draft larger than a version may be is refused with
`draft_too_large`.

| `op` | Arguments | Changes |
|---|---|---|
| `replace_l1` | `{text}` | What the assistant always knows, whole. |
| `put_l2_topic` / `remove_l2_topic` | `{id, description, text}` / `{id}` | One deeper topic; `description` says when to read it. |
| `put_fact` / `remove_fact` | `{fact}` / `{id}` | One fact: `id` (`f0001`), `statement`, `url`, `quote` (verbatim text on that page), `used_in`. |
| `put_page` / `remove_page` | `{page}` / `{id}` | One page of the page map, in the shape `part="page_map"` shows. |
| `put_listing` / `remove_listing` | `{listing}` / `{id}` | One listing of the page map. |
| `put_tool` / `remove_tool` | `{tool}` / `{id}` | One site tool, in the shape of a `tools` entry in the draft's `adapter.json`. |
| `put_component` / `remove_component` | `{page_type, component}` / `{page_type, id}` | One component of a page type. |
| `set_page_type_reads` | `{page_type, reads}` | What is read on a page type. |
| `set_navigation` | `{navigation}` | How a page move goes, whole: `{router, router_global, settle_ms}`, `router` one of `full_load`, `history_push`, `next`, `react_router`. |
| `attach_test_results` | `{adapter_test, background_requests, kit_version}` | What your study kit's run wrote. |
| `replace_stage_spec` | `{spec}` | The site's Stage Spec (`stage.json`), whole; `null` removes it. |
| `put_stage_move` / `remove_stage_move` | `{move}` / `{id}` | One Stage move, in the shape `part="stage"` shows. |

A Stage move edited here keeps the `class` and `args` the site's tools and page
map imply, and changes only its `claims`, `objects`, `verb`, `say`, `doc` and
`notes`. Removing a `site.*` move drops only those changes.

### The checks

Every edit returns `check`:

- **`check.errors`** refuse a submit; **`check.warnings`** do not. Each is
  `{code, path, message}`. Submit when `check.ok` is true.
- **`check.facts`** has a verdict for each new or changed fact:

  | Verdict | Means |
  |---|---|
  | `kept` | The quote is on its page. |
  | `refused` | The page forbids reading, could not be read, or does not carry the quote. |
  | `flagged` | Kept, and shown to the reviewer: the page answered 403 or 429, needs a browser, or the quote is in rendered, PDF or image text. |
  | `unchecked` | Over this call's 20 page reads; the submit checks it. |

- **`check.changed_tools`** and **`check.unproven_tools`** name the site tools
  that need proof.
- **Knowledge states the business's facts only.** New or changed `l1` or topic
  text, or a fact's statement, is an error when it addresses the assistant (an
  instruction) or states a price, stock or reviews: those are read live from
  the page during a call, never kept. Text the base version already had is not
  judged again.

### Prove a changed site tool

A new or changed site tool, or a changed navigation, needs a passing run of the
study kit on the draft:

- Call `get_draft_bundle(tenant, site_id)`. Its `url` downloads the draft as a
  `tar.gz`, for the current `revision` only, and expires ten minutes after it
  is made; fetch a new one after each edit. Treat it as a secret.
- Unpack it and run the kit's `run_adapter_checks.mjs` against it.
- Attach the run's `checks/adapter-test.json` with an `attach_test_results`
  operation.
- Submit with `owner_tested: true`: your statement that you ran the kit on this
  draft.

Without a passing result on its current definition, the submit refuses the tool
by name; it is never dropped. Each tool your kit proved is listed in the
version's `review_flags` for the reviewer to confirm.

### Submit refusals

| Code | Means |
|---|---|
| `draft_not_ready` | A check failed; the errors are in `details`. Every new or changed fact is read from its page at submit. |
| `owner_tested_required` | A site tool proven by your own kit is new or changed, and `owner_tested` was false. |
| `site_run_active` | A study of the site is running; submit when it ends. |
| `concurrent_update` | An edit landed during the submit; check the draft and submit again. |
