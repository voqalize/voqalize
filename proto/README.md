# proto — the Voqalize wire contract

The canonical protobuf schema for the Voqalize voice protocol lives in
[`voqalcloud/frames/frames.proto`](voqalcloud/frames/frames.proto): the `Vql`
frame set plus the lifecycle envelope. Everything a brain sends or receives is
one of these frames.

This is the **contract of record**. The SDKs in this repo are generated from (Go,
Python) or written against (React) this schema; the hosted Voqalize runtime
speaks the same set.

- Field-number policy: `1–30` Vql application frames, `31+` pipeline
  lifecycle / transport frames.
- Opaque dict payloads are JSON-encoded strings (no `google.protobuf.Struct`
  dependency).

## Regenerating stubs

```bash
cd proto
buf generate     # emits Python + Go stubs (see buf.gen.yaml)
buf lint
```

> **Wiring in progress.** `buf.gen.yaml` currently emits to `gen/`. Once the SDKs
> are moved in, the generate targets point at `sdk/python` and `sdk/go` so a
> single `make proto` refreshes the stubs both SDKs consume.

## Namespace

The proto package is currently `voqalcloud.frames` (historical). Standardizing
the public surface on the `voqalize` namespace — proto package, Python import
path, React scope, Go package — is a planned, coordinated rename (it changes
generated symbol paths, so it's done once, deliberately, with tests green).
