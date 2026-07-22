"""Swiggy Instamart MCP — OAuth + first authenticated call, end to end.

A derisk spike for the voice-grocery demo. Proves the whole auth story on a
laptop with **zero asks of Swiggy and no MITM**:

  DCR  ->  PKCE authorize (Swiggy-hosted phone+OTP)  ->  loopback capture
       ->  token exchange  ->  persist  ->  refresh  ->  one real get_addresses call

Why it works (verified against the live endpoints 2026-06-28):
  - https://mcp.swiggy.com/.well-known/oauth-authorization-server advertises
    Dynamic Client Registration, public PKCE clients (token auth "none"), and
    refresh_token grant.
  - http://localhost/callback is on Swiggy's whitelisted redirect list, so our
    loopback listener is a *legitimate* OAuth redirect target, not an intercept.
  - The phone+OTP happens entirely on Swiggy's hosted /auth/authorize page; we
    only ever see the resulting authorization code, then the token.

Stdlib only (urllib + http.server). Run with any Python 3.12+.

Two modes, so token *generation* (privileged, one-time) is decoupled from token
*use* (anyone, headless):

    python3 run.py generate   # account owner: phone+OTP once -> caches ~/.swiggy/tokens.json
    python3 run.py            # anyone: reuse the cached token, refresh if expired, no browser
    python3 run.py run --tools   # reuse + list the tool surface, then exit

Share ~/.swiggy/tokens.json (or this script + that file) and `run` works for
anyone — the demo backend reads the same cached token and passes its
access_token as the session's initial data.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import secrets
import ssl
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# --- Constants (issuer is discovered at runtime; these are the fixed bits) ----

MCP_URL = "https://mcp.swiggy.com/im"  # Instamart streamable-HTTP MCP endpoint
ISSUER_METADATA = "https://mcp.swiggy.com/.well-known/oauth-authorization-server"
SCOPE = "mcp:tools mcp:resources mcp:prompts"
REDIRECT_PORT = 8765
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
MCP_PROTOCOL_VERSION = "2025-06-18"

# Tokens live in ~/.swiggy so they survive across runs and are shareable as a
# single portable artifact — generate once (privileged, phone+OTP), reuse anywhere.
SWIGGY_DIR = Path.home() / ".swiggy"
TOKENS_PATH = SWIGGY_DIR / "tokens.json"  # access + refresh + client_id; chmod 600


# --- Tiny HTTP helpers (stdlib, JSON in / JSON or SSE out) --------------------


def _ssl_context() -> ssl.SSLContext:
    """Verifying context, but tolerant of the python.org-on-macOS CA gotcha.

    python.org's framework Python ships its own CA bundle that often misses the
    roots curl/the browser trust (corporate proxies, newer chains), surfacing as
    'self-signed certificate in certificate chain'. Fall back to the OS bundle at
    /etc/ssl/cert.pem — still full verification, just the trust store curl uses.
    """
    ctx = ssl.create_default_context()
    system_bundle = "/etc/ssl/cert.pem"
    if Path(system_bundle).exists():
        with contextlib.suppress(ssl.SSLError, OSError):
            ctx.load_verify_locations(system_bundle)
    return ctx


_SSL = _ssl_context()


def _http_json(
    url: str, *, method: str = "GET", headers: dict | None = None, body: bytes | None = None
):
    """One request. Returns (status, response_headers, parsed_or_text_body)."""
    req = urllib.request.Request(url, method=method, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, context=_SSL) as resp:
            raw = resp.read()
            return resp.status, dict(resp.headers), _parse_body(dict(resp.headers), raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, dict(e.headers), _parse_body(dict(e.headers), raw)


def _parse_body(headers: dict, raw: bytes):
    text = raw.decode("utf-8", "replace")
    ctype = headers.get("Content-Type", "")
    if "text/event-stream" in ctype:
        # Streamable-HTTP MCP may answer a single JSON-RPC reply as one SSE event.
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        return text
    if "application/json" in ctype:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _form(data: dict) -> bytes:
    return urllib.parse.urlencode(data).encode()


# --- OAuth: discovery, DCR, PKCE, token exchange, refresh --------------------


def discover() -> dict:
    status, _, meta = _http_json(ISSUER_METADATA)
    if status != 200 or not isinstance(meta, dict):
        sys.exit(f"discovery failed: HTTP {status}: {meta}")
    return meta


def register_client(meta: dict) -> str:
    """Dynamic Client Registration -> a public client_id bound to our loopback."""
    body = json.dumps(
        {
            "client_name": "Voqalize Voice Grocery (spike)",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        }
    ).encode()
    status, _, data = _http_json(
        meta["registration_endpoint"],
        method="POST",
        headers={"Content-Type": "application/json"},
        body=body,
    )
    if status not in (200, 201) or not isinstance(data, dict):
        sys.exit(f"DCR failed: HTTP {status}: {data}")
    print(f"  registered client_id={data['client_id']}")
    return data["client_id"]


def _pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    return verifier, challenge


class _CallbackCatcher(BaseHTTPRequestHandler):
    """Single-shot loopback handler: stash ?code=…&state=… and tell the user to return."""

    code: str | None = None
    state: str | None = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        _CallbackCatcher.code = qs.get("code", [None])[0]
        _CallbackCatcher.state = qs.get("state", [None])[0]
        err = qs.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        msg = f"Authorization failed: {err}" if err else "Swiggy connected. Return to the terminal."
        self.wfile.write(
            f"<html><body style='font-family:sans-serif'><h2>{msg}</h2></body></html>".encode()
        )

    def log_message(self, format: str, *args: object) -> None:  # silence the access log
        pass


def authorize(meta: dict, client_id: str) -> dict:
    """Open Swiggy's hosted login (phone+OTP), capture the code at the loopback.

    Returns the token dict (access_token, refresh_token, client_id, …)."""
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)

    server = HTTPServer(("localhost", REDIRECT_PORT), _CallbackCatcher)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("\n  Opening Swiggy login (phone + OTP) in your browser…")
    print(f"  If it doesn't open, paste this URL:\n    {url}\n")
    webbrowser.open(url)

    # Block until the loopback handler captures a code (or the user gives up).
    print(f"  Waiting for the redirect to http://localhost:{REDIRECT_PORT}/callback …")
    while _CallbackCatcher.code is None:
        if not t.is_alive():
            break
        t.join(0.25)
    server.shutdown()

    if _CallbackCatcher.code is None:
        sys.exit("no authorization code captured")
    if _CallbackCatcher.state != state:
        sys.exit("state mismatch — possible CSRF; aborting")
    print("  captured authorization code")
    return _exchange_code(meta, client_id, _CallbackCatcher.code, verifier)


def _exchange_code(meta: dict, client_id: str, code: str, verifier: str) -> dict:
    status, _, tok = _http_json(
        meta["token_endpoint"],
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=_form(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": client_id,
                "code_verifier": verifier,
            }
        ),
    )
    if status != 200 or not isinstance(tok, dict) or "access_token" not in tok:
        sys.exit(f"token exchange failed: HTTP {status}: {tok}")
    tok["client_id"] = client_id
    _save_tokens(tok)
    print("  exchanged code for access + refresh token")
    return tok


def refresh(meta: dict, tokens: dict) -> dict | None:
    if "refresh_token" not in tokens:
        return None
    status, _, tok = _http_json(
        meta["token_endpoint"],
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=_form(
            {
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": tokens["client_id"],
            }
        ),
    )
    if status != 200 or not isinstance(tok, dict) or "access_token" not in tok:
        print(f"  refresh failed (HTTP {status}); will re-login")
        return None
    tok["client_id"] = tokens["client_id"]
    tok.setdefault("refresh_token", tokens["refresh_token"])  # some servers omit it on refresh
    _save_tokens(tok)
    print("  refreshed access token")
    return tok


def _save_tokens(tok: dict) -> None:
    SWIGGY_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    TOKENS_PATH.write_text(json.dumps(tok, indent=2))
    TOKENS_PATH.chmod(0o600)  # it's a bearer credential — owner-only


def _load_tokens() -> dict | None:
    if TOKENS_PATH.exists():
        return json.loads(TOKENS_PATH.read_text())
    return None


# --- MCP: speak just enough Streamable HTTP to make one authenticated call ----


def _mcp(token: str, payload: dict, session_id: str | None) -> tuple[int, dict, object]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return _http_json(MCP_URL, method="POST", headers=headers, body=json.dumps(payload).encode())


def mcp_session(token: str) -> tuple[str | None, list]:
    """initialize -> notifications/initialized -> tools/list. Returns (session_id, tools)."""
    status, hdrs, res = _mcp(
        token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "voqalize-spike", "version": "0.1"},
            },
        },
        None,
    )
    if status == 401:
        return None, []  # caller refreshes and retries
    if status != 200:
        sys.exit(f"initialize failed: HTTP {status}: {res}")
    session_id = hdrs.get("Mcp-Session-Id")
    _mcp(token, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)

    status, _, res = _mcp(token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session_id)
    tools = res.get("result", {}).get("tools", []) if isinstance(res, dict) else []
    return session_id, tools


def mcp_call(token: str, session_id: str | None, name: str, arguments: dict) -> object:
    status, _, res = _mcp(
        token,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        session_id,
    )
    if status != 200:
        return {"_http_status": status, "_body": res}
    return res.get("result") if isinstance(res, dict) else res


# --- Driver ------------------------------------------------------------------


def _verify_call(tokens: dict, meta: dict, *, list_only: bool) -> dict:
    """Open an MCP session with the cached token; refresh once on 401. Returns tokens."""
    print("\nConnecting to the MCP and listing tools…")
    session_id, tools = mcp_session(tokens["access_token"])
    if session_id is None and not tools:
        refreshed = refresh(meta, tokens)
        if not refreshed:
            sys.exit(
                "token expired and refresh failed — re-run `python3 run.py generate` "
                "(the account owner must redo phone+OTP)."
            )
        tokens = refreshed
        session_id, tools = mcp_session(tokens["access_token"])

    print(f"  authenticated. {len(tools)} tools available:")
    for t in tools:
        print(f"    - {t.get('name')}: {t.get('description', '')[:70]}")
    if list_only:
        return tokens

    print("\nCalling get_addresses (real account data)…")
    result = mcp_call(tokens["access_token"], session_id, "get_addresses", {})
    print(json.dumps(result, indent=2)[:2000])
    return tokens


def _print_token_for_paste(access_token: str) -> None:
    """Print the access token in a copy-friendly block (and copy it on macOS).

    This is what the /grocery demo page asks for: run `generate`, copy the token,
    paste it into the page's token field.
    """
    copied = ""
    try:  # best-effort clipboard on macOS
        import subprocess

        subprocess.run(["pbcopy"], input=access_token.encode(), check=True)
        copied = "  (also copied to your clipboard)"
    except (OSError, ValueError):
        pass
    bar = "─" * 60
    print(f"\n  Paste this into the /grocery page's token field{copied}:\n")
    print(f"  ┌{bar}┐")
    print(f"  {access_token}")
    print(f"  └{bar}┘")
    print("\n  Note: this access token expires in ~1h — re-run `generate` for a fresh one.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Swiggy Instamart MCP OAuth spike — generate a token once, reuse it anywhere."
    )
    ap.add_argument(
        "command",
        nargs="?",
        choices=["generate", "run"],
        default="run",
        help="generate = do the phone+OTP OAuth dance and cache a token (run once, by the "
        "account owner); run = reuse the cached ~/.swiggy/tokens.json (default; never opens a browser)",
    )
    ap.add_argument("--tools", action="store_true", help="list the tool surface, then exit")
    args = ap.parse_args()

    print("== Swiggy Instamart MCP — OAuth spike ==")
    meta = discover()
    print(f"issuer: {meta['issuer']}  (DCR + PKCE + refresh_token: confirmed)")

    if args.command == "generate":
        # The "small offline script" path: full interactive OAuth, cache the result.
        print("\nGenerating a fresh token (this opens a browser for phone + OTP)…")
        client_id = register_client(meta)
        tokens = authorize(meta, client_id)  # saves to ~/.swiggy/tokens.json
        _verify_call(tokens, meta, list_only=args.tools)
        print(f"\n✅ Token cached at {TOKENS_PATH} (chmod 600).")
        _print_token_for_paste(tokens["access_token"])
        return

    # The "anyone can run it" path: reuse only — no browser, no OTP.
    tokens = _load_tokens()
    if not tokens or "access_token" not in tokens:
        sys.exit(
            f"no cached token at {TOKENS_PATH}.\n"
            "Run `python3 run.py generate` first (account owner does phone+OTP once), "
            "or drop a shared tokens.json there."
        )
    _verify_call(tokens, meta, list_only=args.tools)
    print("\n✅ Reused cached token: load → (refresh if needed) → live MCP call. No OTP.")


if __name__ == "__main__":
    main()
