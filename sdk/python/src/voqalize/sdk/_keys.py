"""The Voqalize public keys the SDK verifies a connection with.

Voqalize signs the short-lived RS256 token it presents on each brain connection
with a **private** key held only by Voqalize. The matching
**public** keys ship here, inside the SDK, so a customer calling
`run_session(...)` verifies that connection out of the box — no key to fetch,
paste, or rotate by hand. Public keys are public by design; embedding them is
what lets verification be the zero-config default.

Multiple keys are a **trust bundle**: the SDK accepts a token signed by *any* of
them. That is what makes key rotation seamless (publish a new SDK carrying both
the old and new key, roll the signer, later drop the old) and lets one SDK build
verify tokens from more than one Voqalize environment.

Rotation / release process: append the new PEM here and cut an SDK release; never
remove a key until every signer that used it is retired.
"""

from __future__ import annotations

# ── Brain-token signing public keys (RS256, SPKI PEM) ─────────────────────────
#
# Order is irrelevant; each is tried in turn. Keep the human-readable label in
# the comment so ops knows which signer and environment a key belongs to.
VOQALIZE_PUBLIC_KEYS: list[str] = [
    # production brain-token signer.
    """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnZqkG9xDlyjo9ONJruEt
assF7hCeNeS42hGs4U1Z6mht/hWFQoCgK6/DlsRTo1aXvrpFvw7K0WlGZgVXgwm2
iLOeiL1TioqAPt/AW8vta/1coKPLHiRl7UrPL+t8sOgAT9PFhT7THq+G/NWJ6Pog
va/+edcyOsYsvUYTeWxOoVf2sI95NNgIzzvTPMcORAq7/FrlZdAChN6RjrT4Uzjj
t7YGwisdUH/pr52PTiXAEoGwQkut+KzK+prQ+FzLd7vxA4+CBdPNu0FQgs4Rir00
kHs+GpZL175nsEJJ01k+M2hl/atxfFgrFucrLPqEk2Tyydtl9j4aQsNCaUKXUZfw
2QIDAQAB
-----END PUBLIC KEY-----""",
]
