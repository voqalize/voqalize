---
title: Site Agent limits
description: Every bound on Site Agent sites, studies, uploads, drafts, knowledge, settings and preview invites, with what happens past it.
---

Each limit, where it applies, and what happens at it. The page that explains
the feature is linked from each group.

## Sites and keys

| Limit | Value | Past it |
|---|---|---|
| Sites per primary origin, per tenant | One | `site_origin_exists`, naming the site that has it. |
| Previous live key after **Rotate key** | Works for 24 hours | Refused. |

See [Install the snippet](/build/site-agent/install/).

## Studies

| Limit | Value | Past it |
|---|---|---|
| Studies running at once, per site | One, managed or self | `run_in_progress` |
| Managed studies per site per calendar month | 4, refreshes and re-checks included | `run_limit_reached` |
| Quick first read | About 15 pages, within minutes | |
| Self study lifetime | 24 hours from its start | `canceled`, `detail` `expired` |
| Upload size | 50 MiB | Refused |
| Bundle entries | 2,000 | Refused |
| Screenshots in a bundle | 40, at most 500 KiB each | Refused |
| Uploads per upload URL | One; a refusal issues a new URL | The second `PUT` fails. |
| Grader revision rounds | 3 | Recorded only, never a gate. |
| Study kit link | One hour | Fetch a new one. |

See [Studies and self studies](/build/site-agent/study/).

## Drafts and knowledge

| Limit | Value | Past it |
|---|---|---|
| Open drafts per site | One | `draft_exists` |
| Draft lifetime | 7 days from its start | The draft is gone. |
| Operations per `edit_knowledge` call | 50 | Refused |
| Draft size | What a version may hold | `draft_too_large` |
| Fact pages read per edit or check | 20 | The rest are `unchecked` until submit. |
| Draft bundle link | Ten minutes, current revision only | Fetch a new one. |
| What the assistant always knows (`l1`) | 5,500 tokens, estimated as characters ÷ 4 | Refused |
| Deeper topics (`l2`) | 30 | Refused |
| Site tools per site | 48 | Refused |
| `read_site_knowledge` page | 12,000 characters by default, 1,000 to 40,000 | Smaller asks are raised to the floor. |

See [Edit the knowledge](/build/site-agent/knowledge/).

## Settings and notes

| Limit | Value |
|---|---|
| `assistant_name` | 40 characters |
| `greeting` setting | 160 characters |
| Greeting set by a page (`data-greeting`, `window.VoqalizeSite`) | 280 characters; a longer one is ignored |
| Notes | 50, of at most 300 characters each |

See [Settings](/build/site-agent/settings/).

## Preview invites

| Limit | Value |
|---|---|
| Client invite label | 1 to 80 characters |
| Client invite length | 1 to 90 days, default 14 |
| Client invite voice minutes | 1 to 1000, default 60; checked when a call starts, never cutting one short |
| Member invite | 30 days, no minute budget |
| Preview key | 24 hours, refreshed from the invite until it ends |

See [Try it before you install](/build/site-agent/install/#try-it-before-you-install).

## MCP reads

| Limit | Value |
|---|---|
| `list_sites` `limit` | At most 100 |
| Versions per `get_site` page | 10 |

Calls count towards the MCP server's per-tenant rate limit; see
[MCP server](/reference/mcp/#auth-tenancy-and-limits).
