# proto — the Voqalize wire contract

The canonical protobuf schema for the Voqalize voice protocol lives in
[`voqalize/frames/frames.proto`](voqalize/frames/frames.proto): the `Vql`
frame set plus the lifecycle envelope. Everything a brain sends or receives is
one of these frames. The proto package is `voqalize.frames`.

This is the **contract of record**. The SDKs in this repo are generated from
(Python) or written against (React) this schema; the hosted Voqalize runtime
speaks the same set. The wire protocol itself is language-neutral — this proto
is the contract a future Go (or any other language) SDK would regenerate stubs
from.

- Field-number policy: `1–30` Vql application frames, `31+` pipeline
  lifecycle / transport frames.
- Opaque dict payloads are JSON-encoded strings (no `google.protobuf.Struct`
  dependency).

## Regenerating stubs

From the repo root:

```bash
make proto
```

This runs `buf lint` + `buf generate` and copies the generated stub into the
SDK that consumes it — the Python stub into
`sdk/python/src/voqalize/sdk/wire/_frames_pb2.py`. Run it after editing any
`*.proto`. The generated `gen/` tree is git-ignored; the copied-in stub is
committed with the SDK.
