---
title: Site Agent refreshes and review
description: Keeping a Site Agent current after its first version. Refreshes, which ones publish themselves, every state a version can be in, the published, preview and latest versions, and review and publish in full.
---

Your site is live on its first studied version
([The Site Agent](/build/site-agent/)). The site will change after that. This
page is how the assistant keeps up: a refresh writes a new version, and the
review you met on the first version decides whether visitors get it. Along the
way it names every state a version can be in.

## Refresh

A **refresh** is a study run again on a site that already has a studied
version. Voqalize runs it on its servers, as it ran the first, and stores a
new version.

- **Start one with Refresh** in the console. There is no MCP tool that starts a
  study Voqalize runs; over MCP, your coding agent runs a
  [self study](/build/site-agent/self-study/) instead.
- **Re-check** on chosen site tools in the console is a shorter refresh that
  proves just those again, in about 10 minutes.
- **A site may run 4 such studies a calendar month**, refreshes and re-checks
  included. Past that a start is refused with `run_limit_reached`.
- **One study of a site runs at a time**, whoever runs it. Another start is
  refused with `run_in_progress`.

A refresh is compared with the published version, and that comparison decides
what happens to it next.

## Which refreshes publish themselves

The first study's version always waits for review. A refresh waits for review
when it:

- adds, removes or changes a fact that what the assistant always knows (`l1`)
  states;
- adds or changes a site tool that changes the page or sends a form, or raises
  what any site tool may do;
- changes the site's [Stage](/build/stage/) moves, the things the assistant can
  show on the visitor's screen;
- carries a conflict between facts, or did not pass every check;
- ran while the robots agreement was turned off
  ([robots.txt](/build/site-agent/security/#robotstxt)).

A refresh that does none of these is approved and published on its own, and
visitors get it on their next page load. That includes a refresh that rewords
what the assistant always knows without changing the facts it states, changes
the deeper topics or the page map, or removes a site tool.

This is on for every site, and neither the console nor MCP turns it off.
Edits and self studies are never published on their own.

## Every state a version can be in

Each version has a `status`:

| `status` | Means |
|---|---|
| `ready_for_review` | Passed its checks; waiting for a person. |
| `partial` | Stored, but some checks failed; `partial_failures` lists them. Approving and publishing it needs every one named. |
| `approved` | A person approved it. Visitors do not get it until it is published. |
| `published` | What visitors are served now. |
| `superseded` | Was published, then replaced. Publishing it again is a [rollback](/build/site-agent/manage/#roll-back). |
| `rejected` | A person rejected it. A fix is a new version. |
| `invalid` | The study's output failed validation. It cannot be approved. |
| `blocked` | The site turned the reader away; see [bot protection](/build/site-agent/security/#if-your-site-blocks-automated-visitors). It cannot be approved. |

Each version also records its `origin`, what wrote it:

| `origin` | Written by |
|---|---|
| `starter` | The quick first read. |
| `managed_study` | A study Voqalize ran: the first, a refresh or a re-check. |
| `knowledge_edit` | A draft someone submitted ([Edit the knowledge](/build/site-agent/knowledge/)). |
| `self_study` | A study your own coding agent ran ([Self studies](/build/site-agent/self-study/)). |

## Published, preview and latest

A site points at its versions by role, each a field `get_site` shows:

- **`published_version`** is what visitors are served.
- **`preview_version`** is what a [preview](/build/site-agent/preview/) and the
  console's preview show: the newest version that is waiting for review,
  approved or published. A new version becomes the preview as soon as it is
  stored, unless it is `invalid` or `blocked`. Rejecting the preview sends it
  back to the published version.
- **`latest_version`** is the newest stored, whatever its status. The next
  version is numbered `latest_version + 1`.

## Review in full

Review is open to a tenant owner or admin, in the console or over
[MCP](/reference/mcp/#site-agent-tools).

`get_site_version(tenant, site_id, version)` returns the version with its
review state, its checks, its conflicts and its `review_flags`: what the checks
kept but want a person to look at. Read the knowledge itself with
`read_site_knowledge` ([parts](/build/site-agent/knowledge/#what-a-version-holds)),
or try it on your live site with a [preview](/build/site-agent/preview/).

`review_site_version(tenant, site_id, version, decision, resolutions=None, notes="", publish_anyway=None)`,
with `decision` `approve` or `reject`:

- **Only a version waiting for review can be approved**: `ready_for_review` or
  `partial`. Approving changes nothing visitors get.
- **Conflicts.** Where a study found two facts that disagree, approving needs a
  choice for each. `resolutions` is the version's complete list,
  `{conflict_id, chosen_fact_id}`, with `chosen_fact_id` one of the conflict's
  fact ids or `"neither"`. It replaces what is stored, and is saved even if the
  approval is then refused.
- **Partial versions.** A `partial` version also needs `publish_anyway`
  naming every `id` in its `partial_failures`.
- **A version that ran while the robots agreement was turned off** needs a
  person's approval of its own, even where it would otherwise have published
  itself.
- **Notes.** `notes` is kept on the version as `review_notes`.
- **Reject** takes a version in review, or one approved and never published.

## Publish in full

`publish_site_version(tenant, site_id, version, confirm=False, publish_anyway=None)`.

- **Without `confirm: true` nothing is published.** The answer is
  `published: false` and `changes`: what this version would change against the
  live one, in the facts the assistant states, its site tools and its pages.
  Show those to the person and call again with `confirm: true` once they say
  yes.
- **The version must be `approved`**, or `superseded` (a rollback). A
  `starter` version is never published again.
- **A `partial` version** needs `publish_anyway` naming every
  `partial_failures` id again.
- **A site tool nobody has proven on its current definition** refuses the
  publish with `reproof_needed`; a refresh proves it again.

On success the version is `published`, the one before it is `superseded`, and
visitors get it on their next page load.
