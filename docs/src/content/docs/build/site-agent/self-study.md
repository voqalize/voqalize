---
title: Site Agent self studies
description: Running a Site Agent study with your own coding agent over MCP. What the machine needs, the run step by step, the upload and its limits, what the checks refuse, and the states a self study passes through.
---

So far Voqalize has run every study on its servers
([Refreshes and review](/build/site-agent/refresh/)), and you have edited the
knowledge by hand ([Edit the knowledge](/build/site-agent/knowledge/)). A
**self study** is the third way to write a version: your own coding agent runs
the study on your machine, with your own model account, using Voqalize's study
kit. Voqalize checks the result and stores it as a `self_study` version that
waits for review like any other. A self study is never published on its own,
and it does not count towards a site's monthly allowance of studies Voqalize
runs.

```text
  your coding agent                                  Voqalize
  ─────────────────                                  ────────
  start_self_study ────────────────────────────────▶ start.json: kit, upload URL
  run the kit's explorer, then finalize.py
  upload.py ──────────── bundle.tar.gz ────────────▶ stored, not yet checked
  submit_self_study ───────────────────────────────▶ collecting: checks every quote,
                                                       page and site tool
  get_self_study ◀──────────────────────────────────  stored: a new version, waiting
                                                    or refused: reasons, a new URL
```

## What the machine needs

A shell, Python 3.12 or newer, Node, a headless Chromium and open internet. On
Windows, use WSL2. The kit's preflight says in plain words what is missing.

## The run, over MCP

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

## The upload

- One `PUT` of `bundle.tar.gz` to `upload.url`, with every header in
  `upload.headers`, at most `upload.max_bytes` (50 MiB).
- A bundle holds at most 2,000 entries and 40 screenshots of at most 500 KiB
  each.
- The URL takes one upload. A second `PUT` to it fails; a refused upload comes
  with a new URL.
- `kit_version` must be a released kit no older than the oldest Voqalize still
  accepts; otherwise the upload is refused and the answer names the kit to
  download.

## What the checks refuse

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

## States

| `state` | Means |
|---|---|
| `running` | Takes an upload. |
| `collecting` | An upload is being checked. |
| `stored` | `result_version` is the new version, waiting for review. |
| `canceled` | Canceled, or `expired`; `detail` says which. |

`cancel_self_study` frees the site for another study. Versions already stored
stay; the upload URL stops taking uploads.

## What the reviewer sees

The version records the grader's rounds, and each site tool your kit proved is
listed in its `review_flags`: its requests were reported by your run, not
watched by Voqalize's, so the reviewer confirms them before
[approving](/build/site-agent/refresh/#review-in-full).
