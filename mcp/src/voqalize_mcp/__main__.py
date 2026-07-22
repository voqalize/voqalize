"""Entry point: ``voqalize-mcp`` (or ``python -m voqalize_mcp``).

Reads config from the environment, builds the server, and serves over stdio —
the transport Claude Code (and every MCP client) speaks to a local server. A
missing/invalid management key raises ``ConfigError`` here, before any tool runs,
so the developer sees a clear message instead of a 401 mid-session.
"""

from __future__ import annotations

import sys

from voqalize_mcp.config import ConfigError
from voqalize_mcp.server import build_server


def main() -> None:
    try:
        server = build_server()
    except ConfigError as exc:
        print(f"voqalize-mcp: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    server.run()  # stdio transport by default


if __name__ == "__main__":
    main()
