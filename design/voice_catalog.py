#!/usr/bin/env python3
"""Hold the voice roster in the proto and the SDK to what the speech tier
actually serves.

The roster used to be written down wherever it was needed, and every copy went
stale on its own schedule: voices ran in production for weeks that no client
could name, and a page told readers the catalog was two personas long after it
was not. There is now one record of it. The speech tier publishes what its
running process has loaded at ``/voices.json``; everything else reads that.

The proto enum is the one copy this checks, and ``voice_id`` on each enum value
is the join. The enum is deprecated and frozen (``frames.proto``, 2026-10-16): a
brain names a voice by its ``voice_id`` string, so a voice added to the speech
tier needs no proto release. A served voice no enum value claims is therefore
printed, not failed. The other direction still fails: an enum value claiming
an id nothing serves is a name that fails on a live call.

The docs carry no copy to check: ``reference/catalog.md``'s voice table is
rendered in the reader's browser from the same ``/voices.json``
(``docs/public/voice-catalog.js``).

    python3 design/voice_catalog.py check     # the proto, against every node

**The catalog is fetched per A-record, not per hostname.** ``speech.*`` is DNS
round-robin across nodes running their own containers, so one fetch proves one
node. A node that missed a deploy is exactly the state this is looking for.

Needs the generated protobuf module, so run it from a tree where ``make proto``
has been run: ``cd sdk/python && uv run python ../../design/voice_catalog.py check``.
"""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import ssl
import sys

#: The environment the docs describe, and the default to check.
DEFAULT_HOST = "speech.prod.voqalize.com"

#: The document shape this tool understands. The catalog carries its own
#: version so a consumer that would misread a newer one refuses it instead,
#: rather than quietly reading the fields it recognizes and ignoring the rest.
CATALOG_VERSION = 1

#: Engines whose voices left the `Voice` enum while a node may still serve them:
#: a retirement reaches the proto first and each environment with its next
#: speech release. A node serving one is reported, not failed. Remove an engine from here once no node serves it.
#: Kokoro was listed from its retirement (2026-10-26) until speech prod c0adeea
#: (2026-10-28) left no node serving it.
RETIRED_ENGINES: frozenset[str] = frozenset()


def a_records(host: str) -> list[str]:
    """Every address ``host`` resolves to, in a stable order."""
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return sorted({str(info[4][0]) for info in infos})


def fetch(host: str, address: str | None = None) -> dict[str, object]:
    """The catalog one node serves. ``address`` pins which node answers.

    The socket is opened by hand because the node is named twice and
    differently: the TCP connection goes to the address, while SNI and the Host
    header carry the hostname. Without the SNI the reverse proxy cannot tell
    which vhost is being asked for and drops the handshake, which is what
    ``curl --resolve`` is doing for you when you reach for it.
    """
    url = f"https://{address or host}/voices.json"
    context = ssl.create_default_context()
    raw = socket.create_connection((address or host, 443), timeout=15)
    connection = http.client.HTTPSConnection(host, timeout=15)
    connection.sock = context.wrap_socket(raw, server_hostname=host)
    try:
        connection.request("GET", "/voices.json", headers={"Host": host})
        response = connection.getresponse()
        if response.status != 200:
            raise SystemExit(f"{url} answered {response.status} {response.reason}")
        document = json.load(response)
    finally:
        connection.close()
    version = document.get("version")
    if version != CATALOG_VERSION:
        raise SystemExit(
            f"{url} serves catalog version {version!r}, and this tool reads "
            f"{CATALOG_VERSION}. Teach it the new shape rather than guessing at it."
        )
    return document


def voices(document: dict[str, object]) -> list[dict[str, object]]:
    """The voices a client can select: every served voice of an engine not retired."""
    served = document.get("voices")
    if not isinstance(served, list):
        raise SystemExit("the catalog has no `voices` list")
    live = [v for v in served if str(v["engine"]) not in RETIRED_ENGINES]
    return sorted(live, key=lambda v: (str(v["engine"]), str(v["id"])))


def retired(document: dict[str, object]) -> list[str]:
    """The ids of served voices whose engine is retired."""
    served = document.get("voices")
    assert isinstance(served, list)
    return sorted(str(v["id"]) for v in served if str(v["engine"]) in RETIRED_ENGINES)


def proto_voices() -> dict[str, str]:
    """``voice_id`` → enum value name, read out of the descriptor."""
    from voqalize.sdk.wire import _frames_pb2 as pb

    option = pb.DESCRIPTOR.extensions_by_name["voice_id"]
    return {
        value.GetOptions().Extensions[option]: value.name
        for value in pb.Voice.DESCRIPTOR.values
        if value.number != 0
    }


def proto_languages() -> dict[str, str]:
    """``iso_code`` → enum value name, the same join on the other axis."""
    from voqalize.sdk.wire import _frames_pb2 as pb

    option = pb.DESCRIPTOR.extensions_by_name["iso_code"]
    return {
        value.GetOptions().Extensions[option]: value.name
        for value in pb.Language.DESCRIPTOR.values
        if value.number != 0
    }


def cmd_check(args: argparse.Namespace) -> int:
    addresses = a_records(args.host)
    print(f"{args.host} resolves to: {', '.join(addresses)}")

    rosters: dict[str, list[dict[str, object]]] = {}
    for address in addresses:
        document = fetch(args.host, address)
        rosters[address] = voices(document)
        print(f"  {address}: {', '.join(str(v['id']) for v in rosters[address])}")
        for voice_id in retired(document):
            print(f"  · {address} still serves {voice_id}, whose engine is retired")

    problems: list[str] = []

    first = addresses[0]
    for address in addresses[1:]:
        if rosters[address] != rosters[first]:
            problems.append(
                f"{address} and {first} serve different rosters — one of them missed a deploy"
            )

    served = {str(v["id"]) for v in rosters[first]}
    declared = set(proto_voices())
    # The `Voice` enum is frozen and a voice is selected by its `voice_id`
    # string, the way a language past the `Language` enum is (below). A voice
    # added to the speech tier since is reachable without a proto release, so
    # it is printed, not failed.
    for voice_id in sorted(served - declared):
        print(f"  · {voice_id} is a string id only; the frozen `Voice` enum has no value for it")
    for voice_id in sorted(declared - served):
        problems.append(f"`Voice` claims {voice_id} and {args.host} does not serve it")

    # A voice may speak a language the enum cannot spell. Until 0.10.0 that
    # was a voice quietly speaking one language fewer than it does, so it
    # failed here. Since then a language is also a BCP-47 string
    # (`language_tag`), and the enum is closed on purpose: a language added to
    # the speech tier reaches a brain as a string, with no proto release. So it
    # is printed, not failed — the docs table still shows the code, read in
    # the browser from the same roster. The reverse is fine and expected too: the
    # recognizer serves languages no voice speaks, which is what makes hearing
    # one and answering in another a real session.
    codes = set(proto_languages())
    for voice in rosters[first]:
        unknown = sorted(str(code) for code in voice["languages"] if code not in codes)  # type: ignore[union-attr]
        for code in unknown:
            print(
                f"  · {voice['id']} speaks {code!r}, which is a string tag only; no `Language` value names it"
            )

    for problem in problems:
        print(f"  ✗ {problem}")
    if problems:
        return 1
    print("  ✓ the proto and every node agree")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # On the subcommand rather than ahead of it, so `check --host …` reads the
    # way anyone would write it.
    host = argparse.ArgumentParser(add_help=False)
    host.add_argument("--host", default=DEFAULT_HOST, help=f"default {DEFAULT_HOST}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", parents=[host]).set_defaults(run=cmd_check)
    args = parser.parse_args()
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
