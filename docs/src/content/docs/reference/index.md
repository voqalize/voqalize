---
title: API and protocol reference
description: The contracts. The wire, the RTVI plane, the Brain API, the voice and language catalog, error codes, the management API and the MCP server.
---

Use these pages to look up frame fields, callback signatures, error codes,
catalog values and MCP tools. For task-oriented guidance, start with
[Build an agent](/build/) or [Improve the agent](/design/).

## The contracts

| Page | What it holds |
|---|---|
| [The Brain API](/reference/brain/) | Every callback, its signature, and what it is handed. |
| [The wire](/reference/wire/) | Every frame the two ends send, and what each obliges. |
| [The RTVI plane](/reference/rtvi/) | The message whitelist, both directions. |
| [Voice and language](/reference/catalog/) | The voices, the languages, and the pairing rule. |
| [Error codes](/reference/errors/) | Every code, what raised it, and whether it ends the call. |
| [The management API](/reference/management-api/) | The programmatic management boundary and session-start route. |
| [The MCP server](/reference/mcp/) | The tools an agent gets, and what each one reads or writes. |

## What is checked

Contract lists and stable product claims are checked against their sources.

- The `Voice` and `Language` enums are read out of the proto descriptor by the
  SDK rather than written down twice, and a test fails if the two drift.
- Every number, version and count on this site lives once in a facts file next
  to the source it was read out of, and a checker re-reads each one from that
  source on every run. A page may also declare the sentences that are wrong
  *because* of it, and those are searched for in the prose.
- The technical nouns come from a closed lexicon, checked the same way, so one
  concept keeps one word across the proto, the SDK and these pages.

Machine-readable lists are derived where a source exists; explanatory guidance
remains in the task pages.
