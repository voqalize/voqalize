#!/usr/bin/env python3
"""Hold the voice roster — in the proto, in the SDK and in the docs — to what
the speech tier actually serves.

The roster used to be written down wherever it was needed, and every copy went
stale on its own schedule: voices ran in production for weeks that no client
could name, and a page told readers the catalog was two personas long after it
was not. There is now one record of it. The speech tier publishes what its
running process has loaded at ``/voices.json``; everything else reads that.

The proto enum is the one copy we keep on purpose (it is what gives a developer
autocompletion and a name their editor can underline), so it is the one copy
this checks. ``voice_id`` on each enum value is the join: a voice served under
an id no enum value claims is a voice nobody can select, and an enum value
claiming an id nothing serves is a name that fails on a live call.

    python3 design/voice_catalog.py check     # the proto and the docs, against every node
    python3 design/voice_catalog.py render    # rewrite the docs table from the catalog

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
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS_PAGE = REPO / "docs/src/content/docs/reference/catalog.md"

#: The environment whose roster the docs describe.
DEFAULT_HOST = "speech.prod.voqalize.com"

#: The document shape this tool understands. The catalog carries its own
#: version so a consumer that would misread a newer one refuses it instead,
#: rather than quietly reading the fields it recognizes and ignoring the rest.
CATALOG_VERSION = 1

BEGIN = "<!-- voices:begin -->"
END = "<!-- voices:end -->"


def a_records(host: str) -> list[str]:
    """Every address ``host`` resolves to, in a stable order."""
    infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    return sorted({info[4][0] for info in infos})


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
    served = document.get("voices")
    if not isinstance(served, list):
        raise SystemExit("the catalog has no `voices` list")
    return sorted(served, key=lambda v: (str(v["engine"]), str(v["id"])))


def proto_voices() -> dict[str, str]:
    """``voice_id`` → enum value name, read out of the descriptor."""
    from voqalize.sdk.wire import _frames_pb2 as pb

    option = pb.DESCRIPTOR.extensions_by_name["voice_id"]
    return {
        value.GetOptions().Extensions[option]: value.name
        for value in pb.Voice.DESCRIPTOR.values
        if value.number != 0
    }


def table(document: dict[str, object]) -> str:
    """The docs table, as markdown, from one catalog."""
    names = proto_voices()
    rows = [
        "| `Voice` | Voice ID | Sounds like | Speaks |",
        "|---|---|---|---|",
    ]
    for voice in voices(document):
        voice_id = str(voice["id"])
        member = names.get(voice_id)
        if member is None:
            raise SystemExit(
                f"the speech tier serves {voice_id!r} and no `Voice` value claims it. "
                f"Add one to proto/voqalize/frames/frames.proto and run `make proto`."
            )
        spoken = ", ".join(f"`{code}`" for code in voice["languages"])  # type: ignore[union-attr]
        rows.append(
            f"| `Voice.{member.removeprefix('VOICE_')}` | `{voice_id}` | {voice['display']} | {spoken} |"
        )
    return "\n".join(rows)


def rendered_page(document: dict[str, object]) -> str:
    page = DOCS_PAGE.read_text()
    start, end = page.find(BEGIN), page.find(END)
    if start < 0 or end < 0:
        raise SystemExit(f"{DOCS_PAGE} has no {BEGIN} … {END} markers to write between")
    return f"{page[: start + len(BEGIN)]}\n{table(document)}\n{page[end:]}"


def cmd_render(args: argparse.Namespace) -> int:
    document = fetch(args.host)
    DOCS_PAGE.write_text(rendered_page(document))
    print(f"{DOCS_PAGE.relative_to(REPO)}: written from https://{args.host}/voices.json")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    addresses = a_records(args.host)
    print(f"{args.host} resolves to: {', '.join(addresses)}")

    rosters: dict[str, list[dict[str, object]]] = {}
    for address in addresses:
        rosters[address] = voices(fetch(args.host, address))
        print(f"  {address}: {', '.join(str(v['id']) for v in rosters[address])}")

    problems: list[str] = []

    first = addresses[0]
    for address in addresses[1:]:
        if rosters[address] != rosters[first]:
            problems.append(
                f"{address} and {first} serve different rosters — one of them missed a deploy"
            )

    served = {str(v["id"]) for v in rosters[first]}
    declared = set(proto_voices())
    for voice_id in sorted(served - declared):
        problems.append(f"{voice_id} is served and no `Voice` value claims it")
    for voice_id in sorted(declared - served):
        problems.append(f"`Voice` claims {voice_id} and {args.host} does not serve it")

    if not problems and DOCS_PAGE.read_text() != rendered_page(fetch(args.host)):
        problems.append(
            f"{DOCS_PAGE.relative_to(REPO)} is not what the catalog says — "
            f"run `python3 design/voice_catalog.py render`"
        )

    for problem in problems:
        print(f"  ✗ {problem}")
    if problems:
        return 1
    print("  ✓ the proto, the docs and every node agree")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"default {DEFAULT_HOST}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check").set_defaults(run=cmd_check)
    sub.add_parser("render").set_defaults(run=cmd_render)
    args = parser.parse_args()
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
