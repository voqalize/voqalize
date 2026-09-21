# L2 — security, keys and data

Read when: keys and rotation, what is stored and for how long, certifications,
the RTVI whitelist, audit, or privacy.

## Every credential names one agent

There is no tenant-wide key. One existed (`ak_`) and was **removed on
2026-08-12** as part of the security hardening pass, precisely because a key that
opened every agent in a workspace is a key nobody can safely paste anywhere.

- **`sk_`** — secret. Lives in the customer's backend, mints sessions, and is
  also the credential a Cortex brain presents when it dials out.
- **`pk_`** — publishable. Ships in page source. Carries an **origin allowlist
  enforced by the API**; the allowlist must be non-empty, and an empty one denies
  everything rather than allowing everything. A `pk_` may turn recording **off**
  for a call and may **not** turn it on.

Rotation and revocation: `create_api_key`, `list_api_keys`, `revoke_api_key`,
`update_api_key_origins` over MCP. Mint the new one, deploy it, revoke the old
one — revocation takes effect at the next `sessions.connect`, not mid-call.

## How the brain knows the caller is Voqalize

The **brain-connection token**: a short-lived **RS256 JWT** presented on the
inbound WebSocket, with `iss="pygato"`, `aud="brain"`, and `sub` equal to the
session id. The SDK verifies it against embedded public keys; a developer using
the SDK passes the header through and gets verification for free. A brain in
another language verifies the same way.

Binding `sub` to the session id is what stops a captured token being replayed
against a different call.

## The RTVI whitelist is a security property

RTVI messages cross the wire in both directions, but only whitelisted kinds.
`bot-*` and `llm-*` are **deliberately excluded from the brain-to-Voqalize
direction**: those are the voice tier's own assertions about the media — what was
spoken, when speech started, what was heard. A brain must not be able to forge
them, or it could rewrite the record of the call it is a party to.

The whitelist is not a compatibility filter that will be relaxed over time. It is
the boundary.

## What is stored

Stored: the session record, the `init` blob, lifecycle and wire events,
transcripts, Voqalize logs, and audio **only when recording was enabled**.

Not stored: the brain's model history, the brain's prompts, the brain's logs, the
customer's data. They never arrive — the brain runs in the customer's
environment, and the wire carries text and typed events, not model state.

Guidance that follows: **`init` is stored, so send identifiers rather than PII**
and let the brain resolve them against the customer's own database.

**Stored session data, recordings included, is retained for 30 days.** Anyone
with a different retention requirement should raise it before a pilot.

Region: processed and stored in **India**. A US region is planned, not
selectable, no date.

## Certifications and controls

Stated publicly: **ISO 27001**, **SOC 2**, **GDPR compliant**, **DPDP compliant**. Alongside them:
role-based access, a full audit trail, and data-residency controls.

**The SOC 2 report type is not published — never assert Type I or Type II**, and
do not improvise scope or certificate dates. Send the question to
`support@voqalize.com`, which is where the actual documents are.

## VPC

The strongest data answer available: deploy the whole voice tier, speech models
included, inside the customer's own cloud VPC with no external dependency. Then
no audio, transcript or event leaves their estate at all. See
`deployment-and-vpc.md`.

## Why management is OAuth, not a bearer key

There is no bearer-key REST management API for creating agents or minting keys.
Management is **MCP over OAuth**, against a human or an app identity that can be
audited and revoked centrally.

The one HTTP route that takes a key is `sessions.connect` — and it starts a call,
it does not administer anything. Keeping "make a call" and "change the account"
on different credential systems means a leaked page key can, at worst, burn call
minutes, and can never create an agent, read another session or mint another key.
