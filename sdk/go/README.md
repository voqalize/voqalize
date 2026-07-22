# Go brain SDK — *(landing zone)*

The native, pipecat-free Go SDK moves in here. Its own Go module. Consumes the
Go stubs generated from [`../../proto`](../../proto) (a `buf` Go target already
exists) — co-locating proto and this SDK turns stub refresh into a same-repo
`make proto` step.

> Not moved in yet — build order step 1.
