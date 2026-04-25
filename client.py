"""Demo MCP client that authenticates via the OAuth browser flow.

Usage:
    uv run client.py

The client will open your browser for OAuth authorization on first run.
Subsequent runs reuse cached tokens (persisted to disk, encrypted).

Set OAUTH_STORAGE_ENCRYPTION_KEY in your .env to persist tokens across
restarts. Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import asyncio
import json
import os
import stat
import time

from cryptography.fernet import Fernet
from key_value.aio.stores.disk import DiskStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from fastmcp import Client
from fastmcp.client.auth import OAuth


def _secure_storage_permissions(directory: str) -> None:
    os.chmod(directory, stat.S_IRWXU)
    db_path = os.path.join(directory, "cache.db")
    if os.path.exists(db_path):
        os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)


def _build_token_storage() -> FernetEncryptionWrapper:
    key = os.environ.get("OAUTH_STORAGE_ENCRYPTION_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        print(
            "[client] OAUTH_STORAGE_ENCRYPTION_KEY not set — generated an ephemeral key.\n"
            "         Tokens will be stored this session but won't survive a restart.\n"
            f"         To persist tokens, add to your .env:\n"
            f"           OAUTH_STORAGE_ENCRYPTION_KEY={key}"
        )
    directory = os.path.expanduser("~/.fastmcp/oauth-tokens")
    store = DiskStore(directory=directory)
    _secure_storage_permissions(directory)
    return FernetEncryptionWrapper(key_value=store, fernet=Fernet(key))


def _tool_text(result) -> str:
    return result.content[0].text if result.content else "None"


def _format_expiry(expires_at: float | None) -> str:
    if expires_at is None:
        return "no expiry"
    delta = expires_at - time.time()
    if delta <= 0:
        return f"expired {_format_duration(-delta)} ago"
    return f"expires in {_format_duration(delta)}"


def _format_duration(seconds: float) -> str:
    s = int(seconds)
    parts = []
    if s >= 3600:
        parts.append(f"{s // 3600}h")
        s %= 3600
    if s >= 60:
        parts.append(f"{s // 60}m")
        s %= 60
    parts.append(f"{s}s")
    return " ".join(parts)


async def main():
    server_url = os.environ.get("SERVER_URL", "http://localhost:8000/mcp")

    directory = os.path.expanduser("~/.fastmcp/oauth-tokens")
    async with Client(server_url, auth=OAuth(token_storage=_build_token_storage())) as client:
        print(f"\n[client] Connected to {server_url}")

        tools = await client.list_tools()
        print(f"[client] Available tools: {[t.name for t in tools]}")

        result = await client.call_tool("hello", {"name": "OAuth2 World"})
        print(f"\n[client] hello -> {_tool_text(result)}")

        result = await client.call_tool("whoami", {})
        whoami = json.loads(result.content[0].text)
        print(f"[client] whoami -> {json.dumps(whoami, indent=2)}")
        print(f"[client] token {_format_expiry(whoami.get('expires_at'))}")

        # --- Per-user state (SQLite-backed, survives server restarts) ----------------
        print("\n[client] --- Per-user state (persists across runs) ---")

        # Read the visit count from the previous run, then increment and store it.
        # On first run this returns None; on subsequent runs it shows the accumulated count.
        result = await client.call_tool("get_user_value", {"key": "visit_count"})
        prev = _tool_text(result)
        print(f"[client] visit_count from last run -> {prev}")

        new_count = str(int(prev) + 1) if prev != "None" else "1"
        result = await client.call_tool("set_user_value", {"key": "visit_count", "value": new_count})
        print(f"[client] {_tool_text(result)}")


        # --- Per-session state (in-memory, lost on disconnect) -----------------------
        print("\n[client] --- Per-session state (lost when this script exits) ---")

        for _ in range(3):
            result = await client.call_tool("get_session_value", {"key": "session_counter"})
            prev = _tool_text(result)
            new_count = str(int(prev) + 1) if prev != "None" else "1"
            result = await client.call_tool("set_session_value", {"key": "session_counter", "value": new_count})
            print(f"[client] {_tool_text(result)}")

        print("\n[client] Done.")

    _secure_storage_permissions(directory)


if __name__ == "__main__":
    asyncio.run(main())
