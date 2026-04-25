"""Demo MCP client that authenticates via the OAuth browser flow.

Usage:
    uv run client.py

The client will open your browser for OAuth authorization on first run.
Subsequent runs reuse cached tokens (stored in memory for this session).
"""

import asyncio
import json
import os
import time

from fastmcp import Client
from fastmcp.client.auth import OAuth


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

    async with Client(server_url, auth=OAuth()) as client:
        print(f"\n[client] Connected to {server_url}")

        tools = await client.list_tools()
        print(f"[client] Available tools: {[t.name for t in tools]}")

        result = await client.call_tool("hello", {"name": "OAuth2 World"})
        print(f"\n[client] hello -> {result.content[0].text}")

        result = await client.call_tool("whoami", {})
        whoami = json.loads(result.content[0].text)
        print(f"[client] whoami -> {json.dumps(whoami, indent=2)}")
        print(f"[client] token {_format_expiry(whoami.get('expires_at'))}")


if __name__ == "__main__":
    asyncio.run(main())
