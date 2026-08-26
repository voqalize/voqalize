---
title: Reference
description: The contracts. The wire, the RTVI plane, the Brain API, the voice and language catalog, error codes, the management API and the MCP server.
---

Reference is consulted from every stage rather than read in order. These pages
are the contracts: what a frame contains, what a callback is handed, what a code
means, what the catalog serves. They state and do not persuade — the argument for
any of it lives in [Build](/build/) or [Designing for voice](/design/).

## The contracts

| Page | What it holds |
|---|---|
| [The Brain API](/reference/brain/) | Every callback, its signature, and what it is handed. |
| [The wire](/reference/wire/) | Every frame the two ends send, and what each obliges. |
| [The RTVI plane](/reference/rtvi/) | The message whitelist, both directions. |
| [Voice and language](/reference/catalog/) | The voices, the languages, and the pairing rule. |
| [Error codes](/reference/errors/) | Every code, what raised it, and whether it ends the call. |
| [The management API](/reference/management-api/) | Agents, sessions, keys and usage over HTTP. |
| [The MCP server](/reference/mcp/) | The tools an agent gets, and what each one reads or writes. |

## What is checked

Every list on these pages is typed by a person, so every one of them can go stale
— and one did: this reference said *eighteen* MCP tools only after it had said
*sixteen* for as long as nobody counted. So the lists are held to their sources
by machine instead.

- The `Voice` and `Language` enums are read out of the proto descriptor by the
  SDK rather than written down twice, and a test fails if the two drift.
- Every number, version and count on this site lives once in a facts file next
  to the source it was read out of, and a checker re-reads each one from that
  source on every run. A page may also declare the sentences that are wrong
  *because* of it, and those are searched for in the prose.
- The technical nouns come from a closed lexicon, checked the same way, so one
  concept keeps one word across the proto, the SDK and these pages.

**The list is checked; the argument is written.** A hand-kept list goes stale the
week after it ships, and a generated page that tries to explain itself reads like
a machine — so the plan is to render the lists that have a machine-readable
source, starting with the MCP registry, and leave the reasoning where it is.
