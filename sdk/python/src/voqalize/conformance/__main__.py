"""``python -m voqalize.conformance`` — run the conformance suite against a
running brain and print a pass/fail report.

Examples::

    # A brain that verifies pygato tokens against a public key: sign with the
    # matching private key.
    python -m voqalize.conformance \\
        --brain-url ws://127.0.0.1:8787 --private-key ./pygato_priv.pem

    # A brain running allow_unverified (local dev): no token.
    python -m voqalize.conformance --brain-url ws://127.0.0.1:8787 --no-auth

    # Point it at your own brain: the suite probes for the reference command
    # grammar, skips the scenarios that need it, and says so in the verdict.
    python -m voqalize.conformance --brain-url ws://127.0.0.1:8787 --no-auth

    # Spin up the bundled reference brain and self-test the driver:
    python -m voqalize.conformance --self-test
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .report import Report, run_suite


async def _run(args: argparse.Namespace) -> Report:
    private_key_pem: bytes | None = None
    if args.private_key:
        private_key_pem = Path(args.private_key).read_bytes()

    only = args.only.split(",") if args.only else None
    # None ⇒ probe the brain for the reference grammar. The flags are the two
    # overrides, and neither is the normal path any more.
    include_reference = True if args.reference else (False if args.no_reference else None)
    return await run_suite(
        args.brain_url,
        private_key_pem=private_key_pem,
        include_reference=include_reference,
        # An unverified brain can't reject a bad token, so skip auth scenarios.
        include_auth=not args.no_auth,
        only=only,
        default_timeout=args.timeout,
    )


async def _self_test(args: argparse.Namespace) -> Report:
    """Host the bundled reference brain on an ephemeral port and run the full
    catalog against it — proves the driver + checks are internally consistent."""
    from voqalize.sdk.brain import brain_factory
    from voqalize.sdk.inbound import DirectAgent

    from .reference import ConformanceBrain
    from .wire_pygato import generate_keypair

    keypair = generate_keypair()
    agent = DirectAgent(
        factory=brain_factory(ConformanceBrain),
        host="127.0.0.1",
        port=0,
        public_keys=keypair.public_pem,
    )
    port = await agent.start()
    try:
        return await run_suite(
            f"ws://127.0.0.1:{port}",
            private_key_pem=keypair.private_pem,
            include_reference=True,
            default_timeout=args.timeout,
        )
    finally:
        await agent.aclose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voqalize.conformance")
    parser.add_argument("--brain-url", help="ws://host:port base URL of the brain under test")
    parser.add_argument(
        "--private-key", help="PEM file to sign the runtime token the brain verifies"
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="send no Authorization header (brain must run allow_unverified)",
    )
    parser.add_argument(
        "--no-reference",
        action="store_true",
        help="force-skip the scenarios that need the reference command grammar "
        "(by default the suite probes for it and skips them itself)",
    )
    parser.add_argument(
        "--reference",
        action="store_true",
        help="force-run them even if the probe says the brain doesn't speak the grammar",
    )
    parser.add_argument("--only", help="comma-separated scenario names to run")
    parser.add_argument("--timeout", type=float, default=5.0, help="per-wait timeout (s)")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="host the bundled reference brain and run the full catalog against it",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        report = asyncio.run(_self_test(args))
    else:
        if not args.brain_url:
            parser.error("--brain-url is required (or use --self-test)")
        if not args.no_auth and not args.private_key:
            parser.error("pass --private-key to sign a token, or --no-auth")
        report = asyncio.run(_run(args))

    print(report.summary())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
