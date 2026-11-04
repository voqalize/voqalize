---
title: Site Agent studies and self studies
description: How Voqalize reads a site into a version, when a refresh is published without review, and how your coding agent runs a self study over MCP, with the kit, the upload format and its limits.
---

A study reads the site and writes a new [version](/build/site-agent/#concepts):
what the assistant always knows, its deeper topics, every fact with the quote
it came from, the map of the site's pages, and the site tools it proved.

## The quick first read

Adding a site starts it. Within minutes it reads about 15 of the site's key
pages and publishes a `starter` version that tells visitors it is still learning
the site. A starter version cannot be edited, and once replaced it is never
published again.

## Managed studies

Adding a site also starts its first full study, run by Voqalize. Later studies
start from **Refresh** in the console; **Re-check** on chosen actions runs a
shorter refresh of just those, in about 10 minutes. A site may run 4 managed
studies a calendar month; past that a start is refused with
`run_limit_reached`.

The first study's version always waits for review. A refresh is compared with
the published version and waits for review when it:

- adds or changes a fact in what the assistant always knows (`l1`);
- adds or changes a site tool that changes the page or sends a form, or raises
  what a tool may do;
- changes the site's Stage moves;
- carries a conflict between facts, or fails a check.

A refresh that does none of these is approved and published on its own. Edits and self studies are never
published on their own.

## Self studies

A self study is a study your own coding agent runs on your machine, with your
own model account, using Voqalize's study kit. The result is checked by
Voqalize and stored as a `self_study` version that waits for review, exactly
like a managed one. A self study does not count towards the managed-study
allowance.

### What the machine needs

A shell, Python 3.12 or newer, Node, a headless Chromium and open internet. On
Windows, use WSL2. The kit's preflight says in plain words what is missing.

### The run, over MCP

An owner or admin's coding agent, connected to the
[MCP server](/reference/mcp/#site-agent-tools):

- **Calls `start_self_study(tenant, site_id)`.** It is refused with
  `run_in_progress` while any other study of the site runs. The study is
  `refresh` when the site has a study version to start from, else `initial`,
  and it expires 24 hours after it starts.
- **Saves the whole answer as `start.json`** in a new working directory. It
  holds `run_id`; `kit` (a signed link and its `version`); `input`, the
  explorer's first message; `outcome` and `rubric`, which the optional grader
  grades against; `previous`, a refresh's previous files behind signed links;
  `upload` (`method`, `url`, `headers`, `max_bytes`); and `steps`, these steps
  in order. Every URL in it is a secret until its `expires_at`.
- **Downloads and unpacks the kit**, reads its `README.md` or `AGENTS.md`, runs
  its preflight, then its setup.
- **On a refresh, fetches the previous files** with the kit's
  `fetch_previous.py`.
- **Runs the explorer** in a fresh context, with `input` as its first message,
  until the kit's `finalize.py` writes `bundle.tar.gz`.
- **Optionally grades the bundle** with the kit's grader in a separate fresh
  context, for up to 3 revision rounds.
- **Uploads `bundle.tar.gz`** with the kit's `upload.py`.
- **Calls `submit_self_study`** with the bundle's SHA-256 (`bundle.sha256`), the
  kit's `VERSION`, the grader record `{ran, rounds}`, and `owner_tested: true`
  when a site tool proven only by this run is new or changed.
- **Polls `get_self_study`** until the study is `stored` or the upload is
  refused.

The kit link lasts one hour; `get_draft_bundle` and `start_knowledge_edit` hand
out a fresh one.

### The upload

- One `PUT` of `bundle.tar.gz` to `upload.url`, with every header in
  `upload.headers`, at most `upload.max_bytes` (50 MiB).
- A bundle holds at most 2,000 entries and 40 screenshots of at most 500 KiB
  each.
- The URL takes one upload. A second `PUT` to it fails; a refused upload comes
  with a new URL.
- `kit_version` must be a released kit no older than the oldest Voqalize still
  accepts; otherwise the upload is refused and the answer names the kit to
  download.

### What the checks refuse

After `submit_self_study` the study is `collecting`: Voqalize reads every fact's
page, the page map and every site tool's proof. Any one of these refuses the
whole upload, and no version is stored from it:

- a quote that is not on its page;
- a page the reader may not read;
- a site tool that is unproven or dangerous;
- an error in the site tools' definitions;
- a bundle that does not validate.

`get_self_study` then lists each reason as `{code, path, message}` and gives the
next upload URL. Fix, upload again, and submit again.

### States

| `state` | Means |
|---|---|
| `running` | Takes an upload. |
| `collecting` | An upload is being checked. |
| `stored` | `result_version` is the new version, waiting for review. |
| `canceled` | Canceled, or `expired`; `detail` says which. |

`cancel_self_study` frees the site for another study. Versions already stored
stay; the upload URL stops taking uploads.

### What the reviewer sees

The version records the grader's rounds, and each site tool your kit proved is
listed in its `review_flags`: its requests were reported by your run, not
watched by Voqalize's, so the reviewer confirms them.
