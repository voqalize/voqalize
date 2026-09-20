---
title: API and protocol reference
description: The contracts. The wire, the RTVI plane, the Brain API, the voice and language catalog, error codes, the HTTP API and the MCP server.
---

Look up frame fields, callback signatures, error codes, catalog values and MCP
tools here. For task-oriented guidance, start with [Build an
agent](/build/) or [Improve the agent](/design/).

- [The Brain API](/reference/brain/) — every callback, its signature, and what it is handed.
- [The wire](/reference/wire/) — every frame each end sends, and what it obliges.
- [The RTVI plane](/reference/rtvi/) — the message whitelist, both directions.
- [Voice and language](/reference/catalog/) — the voices, the languages, and the pairing rule.
- [Error codes](/reference/errors/) — every code, what raised it, and whether it ends the call.
- [The HTTP API](/reference/http-api/) — `sessions.connect`, and why management is MCP instead.
- [The MCP server](/reference/mcp/) — the tools an agent gets, and what each one reads or writes.

## What is checked

Contract lists and stable product claims are checked against their sources.

- The `Voice` and `Language` enums are read out of the proto descriptor by the
  SDK rather than written down twice, and a test fails if they drift.
- Every number, version and date on this site lives once in a facts file next
  to the source it was read out of, and a checker re-reads each one from that
  source on every run. A page may also declare the sentences that are wrong
  *because* of it, and those are searched for in the prose.
- The technical nouns come from a closed lexicon, checked the same way, so one
  concept keeps one word across the proto, the SDK and these pages.

Machine-readable lists are derived where a source exists; explanatory guidance
remains in the task pages.
