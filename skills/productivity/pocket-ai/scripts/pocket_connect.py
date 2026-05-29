#!/usr/bin/env python3
"""Pocket AI MCP OAuth connector for SiteKick/Hermes.

This script supports chat/Telegram paste-back OAuth:

  1. python3 pocket_connect.py start --user-id telegram-123
  2. Send the printed authorization URL to the user.
  3. User approves access and pastes back the localhost callback URL.
  4. python3 pocket_connect.py complete --user-id telegram-123 'http://localhost:.../oauth/callback?code=...&state=...'
  5. python3 pocket_connect.py list-tools --user-id telegram-123

Tokens are stored under the active Hermes profile, defaulting to:
  ~/.hermes/profiles/sitekick/mcp-tokens/pocket/<safe-user-id>.tokens.json

The script never prints access or refresh tokens.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

POCKET_MCP_URL = "https://public.heypocketai.com/mcp"
RESOURCE_METADATA_URL = "https://public.heypocketai.com/.well-known/oauth-protected-resource"
DEFAULT_SCOPE = "mcp:read"
DEFAULT_PROFILE = "sitekick"
DEFAULT_HERMES_HOME = Path.home() / ".hermes" / "profiles" / DEFAULT_PROFILE


class ConnectorError(RuntimeError):
    pass


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", str(DEFAULT_HERMES_HOME))).expanduser()


def token_dir() -> Path:
    return hermes_home() / "mcp-tokens" / "pocket"


def safe_user_id(user_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.@-]+", "_", user_id.strip())
    return cleaned[:120] or "default"


def pending_path(user_id: str) -> Path:
    return token_dir() / f"{safe_user_id(user_id)}.pending.json"


def token_path(user_id: str) -> Path:
    return token_dir() / f"{safe_user_id(user_id)}.tokens.json"


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except PermissionError:
        pass


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    ensure_private_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except PermissionError:
        pass
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except PermissionError:
        pass


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConnectorError(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def http_json(url: str, *, method: str = "GET", data: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    body: bytes | None = None
    req_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise ConnectorError(f"HTTP {e.code} from {url}: {detail[:500]}") from e
    except urllib.error.URLError as e:
        raise ConnectorError(f"Network error from {url}: {e}") from e


def http_form(url: str, data: dict[str, Any]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise ConnectorError(f"Token exchange failed with HTTP {e.code}: {detail[:500]}") from e


def discover_oauth() -> dict[str, Any]:
    resource_meta = http_json(RESOURCE_METADATA_URL)
    auth_servers = resource_meta.get("authorization_servers") or []
    if not auth_servers:
        raise ConnectorError("Pocket resource metadata did not include authorization_servers")
    issuer = auth_servers[0].rstrip("/")
    auth_meta = http_json(f"{issuer}/.well-known/oauth-authorization-server")
    required = ["authorization_endpoint", "token_endpoint", "registration_endpoint"]
    missing = [k for k in required if not auth_meta.get(k)]
    if missing:
        raise ConnectorError(f"Pocket OAuth metadata missing: {', '.join(missing)}")
    auth_meta["resource"] = resource_meta.get("resource", POCKET_MCP_URL)
    auth_meta["issuer"] = auth_meta.get("issuer", issuer)
    return auth_meta


def register_client(auth_meta: dict[str, Any], redirect_uri: str, client_name: str) -> dict[str, Any]:
    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": DEFAULT_SCOPE,
    }
    return http_json(auth_meta["registration_endpoint"], method="POST", data=payload)


def command_start(args: argparse.Namespace) -> int:
    auth_meta = discover_oauth()
    state = b64url(secrets.token_bytes(32))
    verifier = b64url(secrets.token_bytes(32))
    challenge = b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    redirect_uri = f"http://localhost:{args.port}/oauth/callback"
    client = register_client(auth_meta, redirect_uri, args.client_name)
    client_id = client.get("client_id")
    if not client_id:
        raise ConnectorError("Dynamic client registration did not return client_id")

    pending = {
        "created_at": int(time.time()),
        "user_id": args.user_id,
        "state": state,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "client": client,
        "auth_meta": auth_meta,
        "scope": args.scope,
        "resource": auth_meta.get("resource", POCKET_MCP_URL),
    }
    write_private_json(pending_path(args.user_id), pending)

    q = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": pending["resource"],
        "scope": args.scope,
    }
    auth_url = auth_meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(q)
    print("POCKET_OAUTH_READY")
    print(f"user_id: {args.user_id}")
    print(f"pending_file: {pending_path(args.user_id)}")
    print("authorization_url:")
    print(auth_url)
    print("\nSend that URL to the user. After approval, ask them to paste back the full localhost callback URL.")
    return 0


def parse_callback(callback_url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(callback_url.strip())
    params = urllib.parse.parse_qs(parsed.query)
    code = (params.get("code") or [""])[0]
    state = (params.get("state") or [""])[0]
    if not code or not state:
        raise ConnectorError("Callback URL must include both code and state query parameters")
    return code, state


def command_complete(args: argparse.Namespace) -> int:
    pending_file = pending_path(args.user_id)
    pending = read_json(pending_file)
    code, returned_state = parse_callback(args.callback_url)
    if returned_state != pending.get("state"):
        raise ConnectorError("OAuth state mismatch. Refusing to exchange code.")
    client = pending["client"]
    auth_meta = pending["auth_meta"]
    token_req = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending["redirect_uri"],
        "client_id": client["client_id"],
        "code_verifier": pending["code_verifier"],
        "resource": pending.get("resource", POCKET_MCP_URL),
    }
    # Public client; Pocket advertises token_endpoint_auth_methods_supported=['none'].
    tokens = http_form(auth_meta["token_endpoint"], token_req)
    if "access_token" not in tokens:
        raise ConnectorError("Token endpoint did not return access_token")
    expires_in = int(tokens.get("expires_in") or 0)
    record = {
        "connected_at": int(time.time()),
        "expires_at": int(time.time()) + expires_in if expires_in else None,
        "user_id": args.user_id,
        "mcp_url": POCKET_MCP_URL,
        "resource": pending.get("resource", POCKET_MCP_URL),
        "scope": tokens.get("scope", pending.get("scope", DEFAULT_SCOPE)),
        "token_type": tokens.get("token_type", "Bearer"),
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "client": client,
        "auth_meta": auth_meta,
    }
    write_private_json(token_path(args.user_id), record)
    try:
        pending_file.unlink()
    except FileNotFoundError:
        pass
    print("POCKET_CONNECTED")
    print(f"user_id: {args.user_id}")
    print(f"token_file: {token_path(args.user_id)}")
    print("access_token: [stored, not printed]")
    print("refresh_token: [stored, not printed]" if record.get("refresh_token") else "refresh_token: [not returned]")
    if args.verify:
        tools = asyncio.run(list_pocket_tools(args.user_id))
        print("verified_tools:")
        for name in tools:
            print(f"- {name}")
    return 0


def load_tokens(user_id: str) -> dict[str, Any]:
    record = read_json(token_path(user_id))
    if not record.get("access_token"):
        raise ConnectorError(f"No access_token in {token_path(user_id)}")
    return record


def command_status(args: argparse.Namespace) -> int:
    p = token_path(args.user_id)
    if not p.exists():
        pend = pending_path(args.user_id)
        if pend.exists():
            data = read_json(pend)
            print("POCKET_PENDING")
            print(f"user_id: {args.user_id}")
            print(f"created_at: {data.get('created_at')}")
            print(f"pending_file: {pend}")
            return 1
        print("POCKET_NOT_CONNECTED")
        print(f"user_id: {args.user_id}")
        return 1
    data = read_json(p)
    now = int(time.time())
    expires_at = data.get("expires_at")
    print("POCKET_CONNECTED")
    print(f"user_id: {args.user_id}")
    print(f"token_file: {p}")
    print(f"scope: {data.get('scope')}")
    print(f"expires_at: {expires_at}")
    if expires_at:
        print(f"seconds_until_expiry: {int(expires_at) - now}")
    print("access_token: [stored, not printed]")
    print("refresh_token: [stored, not printed]" if data.get("refresh_token") else "refresh_token: [not stored]")
    return 0


def command_refresh(args: argparse.Namespace) -> int:
    record = load_tokens(args.user_id)
    refresh_token = record.get("refresh_token")
    if not refresh_token:
        raise ConnectorError("No refresh_token stored; run start/complete again")
    auth_meta = record["auth_meta"]
    client = record["client"]
    token_req = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client["client_id"],
        "resource": record.get("resource", POCKET_MCP_URL),
    }
    tokens = http_form(auth_meta["token_endpoint"], token_req)
    if "access_token" not in tokens:
        raise ConnectorError("Refresh did not return access_token")
    expires_in = int(tokens.get("expires_in") or 0)
    record.update(
        {
            "refreshed_at": int(time.time()),
            "expires_at": int(time.time()) + expires_in if expires_in else None,
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token", refresh_token),
            "scope": tokens.get("scope", record.get("scope")),
            "token_type": tokens.get("token_type", record.get("token_type", "Bearer")),
        }
    )
    write_private_json(token_path(args.user_id), record)
    print("POCKET_REFRESHED")
    print(f"user_id: {args.user_id}")
    print("access_token: [stored, not printed]")
    return 0


async def list_pocket_tools(user_id: str) -> list[str]:
    record = load_tokens(user_id)
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except Exception as e:  # pragma: no cover
        raise ConnectorError("Python mcp package is required to verify Pocket tools") from e
    headers = {"Authorization": f"Bearer {record['access_token']}"}
    async with streamablehttp_client(POCKET_MCP_URL, headers=headers, timeout=45) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return [tool.name for tool in tools.tools]


def command_list_tools(args: argparse.Namespace) -> int:
    tools = asyncio.run(list_pocket_tools(args.user_id))
    print("POCKET_TOOLS")
    for name in tools:
        print(f"- {name}")
    return 0


def command_configure_hermes(args: argparse.Namespace) -> int:
    """Optional single-user runtime config helper.

    This writes the current access token into config.yaml as an HTTP Authorization
    header so native MCP discovery can load Pocket after Hermes restart. This is
    useful for a single owner/admin profile. For multi-user Telegram, keep using
    per-user token files and do not share one global MCP connection.
    """
    if yaml is None:
        raise ConnectorError("PyYAML is required for configure-hermes")
    record = load_tokens(args.user_id)
    cfg_path = Path(args.config).expanduser()
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg.setdefault("mcp_servers", {})
    cfg["mcp_servers"][args.server_name] = {
        "url": POCKET_MCP_URL,
        "headers": {"Authorization": f"Bearer {record['access_token']}"},
        "timeout": 120,
        "connect_timeout": 60,
    }
    backup = cfg_path.with_suffix(cfg_path.suffix + f".bak-{int(time.time())}")
    backup.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    print("HERMES_CONFIG_UPDATED")
    print(f"config: {cfg_path}")
    print(f"backup: {backup}")
    print(f"server: {args.server_name}")
    print("Note: restart Hermes for native MCP tool discovery. Token is stored in config.yaml; use only for a single-user/admin profile.")
    return 0


def add_user_id_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user-id", default="sitekick-owner", help="Stable user key, e.g. sitekick-owner or telegram-123456.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Connect Pocket AI MCP to SiteKick/Hermes using OAuth paste-back.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="Start OAuth and print authorization URL.")
    add_user_id_arg(p)
    p.add_argument("--port", type=int, default=11226, help="Localhost callback port embedded in redirect URI.")
    p.add_argument("--scope", default=DEFAULT_SCOPE)
    p.add_argument("--client-name", default="SiteKick Pocket Connector")
    p.set_defaults(func=command_start)

    p = sub.add_parser("complete", help="Complete OAuth using pasted localhost callback URL.")
    add_user_id_arg(p)
    p.add_argument("callback_url")
    p.add_argument("--verify", action="store_true", help="List Pocket tools after token exchange.")
    p.set_defaults(func=command_complete)

    p = sub.add_parser("status", help="Show redacted connection status.")
    add_user_id_arg(p)
    p.set_defaults(func=command_status)

    p = sub.add_parser("refresh", help="Refresh stored Pocket access token.")
    add_user_id_arg(p)
    p.set_defaults(func=command_refresh)

    p = sub.add_parser("list-tools", help="Verify connection by listing Pocket MCP tools.")
    add_user_id_arg(p)
    p.set_defaults(func=command_list_tools)

    p = sub.add_parser("configure-hermes", help="Optional: add current user's token to Hermes mcp_servers.pocket config.")
    add_user_id_arg(p)
    p.add_argument("--config", default=str(hermes_home() / "config.yaml"))
    p.add_argument("--server-name", default="pocket")
    p.set_defaults(func=command_configure_hermes)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except ConnectorError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
