package cortex

// Voqalize's embedded platform public keys.
//
// PyGato signs the short-lived RS256 token it presents on each direct brain
// connection (/s/{session_id}) with a PRIVATE key held only by Voqalize. The
// matching PUBLIC keys are shipped here, inside the SDK, so a DirectServer
// verifies our connection out of the box — no key to fetch, paste, or rotate by
// hand. Public keys are public by design; embedding them is safe and is what
// lets verification be the zero-config default.
//
// Multiple keys are a trust bundle: a token signed by ANY of them is accepted.
// That makes rotation seamless (ship an SDK carrying both old and new key, roll
// the signer, later drop the old). Rotation/release: append the new PEM and cut a
// release; never remove a key until every signer that used it is retired. These
// must stay in sync with the production PyGato signer — the same key the
// production control plane and Cortex already verify against.
const platformPublicKeysPEM = `
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnZqkG9xDlyjo9ONJruEt
assF7hCeNeS42hGs4U1Z6mht/hWFQoCgK6/DlsRTo1aXvrpFvw7K0WlGZgVXgwm2
iLOeiL1TioqAPt/AW8vta/1coKPLHiRl7UrPL+t8sOgAT9PFhT7THq+G/NWJ6Pog
va/+edcyOsYsvUYTeWxOoVf2sI95NNgIzzvTPMcORAq7/FrlZdAChN6RjrT4Uzjj
t7YGwisdUH/pr52PTiXAEoGwQkut+KzK+prQ+FzLd7vxA4+CBdPNu0FQgs4Rir00
kHs+GpZL175nsEJJ01k+M2hl/atxfFgrFucrLPqEk2Tyydtl9j4aQsNCaUKXUZfw
2QIDAQAB
-----END PUBLIC KEY-----
` // production PyGato brain-token signer
