---
title: Review and publish a Site Agent version
description: Who may approve a site version, how conflicts and partial versions are settled, what publishing changes, and how to roll back to an earlier version.
---

A stored version reaches visitors in two separate steps: a person approves it,
then publishes it. Both are open to a tenant owner or admin, in the console or
over [MCP](/reference/mcp/#site-agent-tools).

## Read the version

`get_site_version(tenant, site_id, version)` returns the version with its review
state, its checks, its conflicts and its `review_flags`. Read the knowledge
itself with `read_site_knowledge`, or try it on the live site with a
[preview invite](/build/site-agent/install/#try-it-before-you-install): a new
version is the site's preview as soon as it is stored.

## Approve or reject

`review_site_version(tenant, site_id, version, decision, resolutions=None, notes="", publish_anyway=None)`,
with `decision` `approve` or `reject`.

- **Conflicts.** Where a study found two facts that disagree, approving needs a
  choice for each. `resolutions` is the version's complete list,
  `{conflict_id, chosen_fact_id}`, with `chosen_fact_id` one of the conflict's
  fact ids or `"neither"`. It replaces what is stored, and is saved even if the
  approval is then refused.
- **Partial versions.** A `partial` version also needs `publish_anyway`
  naming every `id` in its `partial_failures`.
- **Notes.** `notes` is kept on the version as `review_notes`.
- **Reject** takes a version in review, or one approved and never published.
  The site's preview goes back to the published version.

Approving does not change what visitors get.

## Publish

`publish_site_version(tenant, site_id, version, confirm=False, publish_anyway=None)`.

- **Without `confirm: true` nothing is published.** The answer is
  `published: false` and `changes`: what this version would change against the
  live one, in the facts the assistant states, its site tools and its pages.
  Show those to the person and call again with `confirm: true` once they say
  yes.
- **The version must be `approved`**, or `superseded` (a rollback, below).
- **A `partial` version** needs `publish_anyway` naming every
  `partial_failures` id again.
- **A site tool nobody has proven on its current definition** refuses the
  publish with `reproof_needed`.

On success the version is `published`, the one before it is `superseded`, and
visitors get it on their next page load. `get_site` shows the new
`published_version`.

## Roll back

Publish an earlier `superseded` version. It needs no new approval, and goes
through the same `confirm` step. A rollback to a `partial` version needs
`publish_anyway` again.

## Refreshes that skip review

A managed refresh that changes nothing a person must read is approved and
published on its own; [Studies](/build/site-agent/study/#managed-studies) lists
what makes a refresh wait. Edits and self studies always wait.
