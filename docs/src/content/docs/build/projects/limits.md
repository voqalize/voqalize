---
title: Project limits
description: Every bound on projects, studies, uploads, drafts, knowledge, settings and preview invites, with what happens past it.
---

The last page of the section gathers every bound the earlier pages mention:
each limit, where it applies, and what happens at it. The page that explains
the feature is linked from each group.

## Projects and keys

| Limit | Value | Past it |
|---|---|---|
| Projects per primary origin, per workspace | One | `project_origin_exists`, naming the project that has it. |
| Previous live key after **Rotate key** | Works for 24 hours | Refused. |

See [Roll back, roles and the console](/build/projects/manage/#replace-the-key).

## Studies

| Limit | Value | Past it |
|---|---|---|
| Studies running at once, per project | One, managed or self | `run_in_progress` |
| Managed studies per project per calendar month | 4, refreshes and re-checks included | `run_limit_reached` |
| Quick first read | The home page and up to 10 key pages, within minutes | |
| Self study lifetime | 24 hours from its start | `canceled`, `detail` `expired` |
| Upload size | 50 MiB | Refused |
| Bundle entries | 2,000 | Refused |
| Screenshots in a bundle | 40, at most 500 KiB each | Refused |
| Uploads per upload URL | One; a refusal issues a new URL | The second `PUT` fails. |
| Grader revision rounds | 3 | Recorded only, never a gate. |
| Study kit link | One hour | Fetch a new one. |

See [Refreshes and review](/build/projects/refresh/#refresh) and [Self studies](/build/projects/self-study/).

## Drafts and knowledge

| Limit | Value | Past it |
|---|---|---|
| Open drafts per project | One | `draft_exists` |
| Draft lifetime | 7 days from its start | The draft is gone. |
| Operations per `edit_knowledge` call | 50 | Refused |
| Draft size | What a version may hold | `draft_too_large` |
| Fact pages read per edit or check | 20 | The rest are `unchecked` until submit. |
| Draft bundle link | Ten minutes, current revision only | Fetch a new one. |
| What the assistant always knows (`l1`) | 5,500 tokens, estimated as characters ÷ 4 | Refused |
| Deeper topics (`l2`) | 30 | Refused |
| Site tools per project | 48 | Refused |
| `read_project_knowledge` page | 12,000 characters by default, 1,000 to 40,000 | Smaller asks are raised to the floor. |

See [Edit the knowledge](/build/projects/knowledge/).

## Settings and notes

| Limit | Value |
|---|---|
| `assistant_name` | 40 characters |
| `greeting` setting | 160 characters |
| Greeting set by a page (`data-greeting`, `window.VoqalizeSite`) | 280 characters; a longer one is ignored |
| `voice.instructions`, per language | 500 characters |
| Notes | 50, of at most 300 characters each |

See [Settings](/build/projects/settings/) and [Notes in the console](/build/projects/knowledge/#notes-in-the-console).

## Previews

| Limit | Value |
|---|---|
| Client invite label | 1 to 80 characters |
| Client invite length | 1 to 90 days, default 14 |
| Client invite voice minutes | 1 to 1000, default 60; checked when a call starts, never cutting one short |
| Member invite | 30 days, no minute budget |
| Preview key | 24 hours, refreshed from the invite until it ends |
| **Try it live** token | 10 minutes, one use |

See [Previews and invites](/build/projects/preview/).

## MCP reads

| Limit | Value |
|---|---|
| `list_projects` `limit` | At most 100 |
| Versions per `get_project` page | 10 |

Calls count towards the MCP server's per-workspace rate limit; see
[MCP server](/reference/mcp/#auth-workspaces-and-limits).
