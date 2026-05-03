"""Demo MCP client that authenticates via the OAuth browser flow.

Usage:
    uv run client.py                                  # browser OAuth flow
    TOKEN=<bearer-token> uv run client.py             # pre-issued bearer token
    TOKEN=$(uv run get_gitlab_token.py) uv run client.py

When TOKEN is set, the client skips the browser flow and sends the value
as a bearer token. Useful for headless / CI scenarios, or when paired with
`get_gitlab_token.py` to use a GitLab id_token directly.

Otherwise the client opens your browser for OAuth authorization on first
run and reuses cached tokens (persisted to disk, encrypted) on subsequent
runs.

Set OAUTH_STORAGE_ENCRYPTION_KEY in your .env to persist tokens across
restarts. Generate a key with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import asyncio
import json
import logging
import os
import stat
import sys
import time

from cryptography.fernet import Fernet
from key_value.aio.stores.disk import DiskStore
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

from fastmcp import Client
from fastmcp.client.auth import BearerAuth, OAuth


def _secure_storage_permissions(directory: str) -> None:
    # os.chmod is a no-op on Windows — POSIX permission bits do not apply.
    # Bail out explicitly rather than silently appearing to harden the cache.
    # Windows users get whatever the default ACL on the home directory is;
    # for stronger at-rest protection on Windows, encrypt the volume or use
    # a different token store.
    if os.name != "posix":
        return
    os.chmod(directory, stat.S_IRWXU)
    db_path = os.path.join(directory, "cache.db")
    if os.path.exists(db_path):
        os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)


def _build_token_storage() -> tuple[object, str | None]:
    """Return ``(token_store, directory_to_chmod_or_None)``.

    When OAUTH_STORAGE_ENCRYPTION_KEY is set, persist tokens to an encrypted
    on-disk store. When it isn't, fall back to in-memory storage — writing
    Fernet-encrypted blobs with an ephemeral key would leave unrecoverable
    garbage in ~/.fastmcp/oauth-tokens on every run.
    """
    key = os.environ.get("OAUTH_STORAGE_ENCRYPTION_KEY")
    if not key:
        # stderr so the message can't pollute stdout (matters when callers
        # capture output, e.g. TOKEN=$(uv run client.py)).
        print(
            "[client] OAUTH_STORAGE_ENCRYPTION_KEY not set — using in-memory token storage.\n"
            "         Tokens will be lost when this script exits.\n"
            "         To persist across runs, generate a key with:\n"
            '           python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
            "         and add it to .env as OAUTH_STORAGE_ENCRYPTION_KEY.",
            file=sys.stderr,
        )
        return MemoryStore(), None

    directory = os.path.expanduser("~/.fastmcp/oauth-tokens")
    store = DiskStore(directory=directory)
    _secure_storage_permissions(directory)
    return FernetEncryptionWrapper(key_value=store, fernet=Fernet(key)), directory


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


class _OAuthRetryFilter(logging.Filter):
    """Replace expected OAuth retry log noise with clean one-line status messages.

    The mcp library logs a full traceback whenever the authorization flow fails
    on the way to fastmcp's retry handler. These two cases are normal recovery
    paths, not real errors, so we swap the noisy output for something readable.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()

        if msg.startswith("Token refresh failed:"):
            code = msg.split(": ", 1)[1]
            print(
                f"[client] Cached token is no longer valid ({code}) — will re-authenticate.",
                file=sys.stderr,
            )
            return False

        if msg == "OAuth flow error" and record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type is not None and exc_type.__name__ == "ClientNotFoundError":
                print(
                    "[client] Cached OAuth client not recognised by server"
                    " — clearing credentials and re-registering.",
                    file=sys.stderr,
                )
                return False

        return True


logging.getLogger("mcp.client.auth.oauth2").addFilter(_OAuthRetryFilter())


async def main():
    server_url = os.environ.get("SERVER_URL", "http://localhost:8000/mcp")
    token = os.environ.get("TOKEN")

    if token:
        auth = BearerAuth(token)
        directory = None
        print(f"[client] Using bearer token from $TOKEN (skipping browser OAuth flow)")
    else:
        storage, directory = _build_token_storage()
        auth = OAuth(token_storage=storage)

    async with Client(server_url, auth=auth) as client:
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

    if directory is not None:
        _secure_storage_permissions(directory)


if __name__ == "__main__":
    asyncio.run(main())
