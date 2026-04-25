"""Demo MCP client that authenticates with a bearer token.

Usage:
    # Generate a token and pass it in:
    TOKEN=$(uv run generate_token.py) uv run client.py

    # Or set manually:
    TOKEN=<your-jwt> uv run client.py
"""

import asyncio
import os
import subprocess
import sys

from fastmcp import Client
from fastmcp.client.auth import BearerAuth


async def main():
    token = os.environ.get("TOKEN")
    if not token:
        # Auto-generate a local dev token if not provided
        result = subprocess.run(
            [sys.executable, "generate_token.py"],
            capture_output=True,
            text=True,
            check=True,
        )
        token = result.stdout.strip()
        print(f"[client] Generated local dev token: {token[:30]}...")

    server_url = os.environ.get("SERVER_URL", "http://localhost:8000/mcp")

    async with Client(server_url, auth=BearerAuth(token)) as client:
        print(f"\n[client] Connected to {server_url}")

        tools = await client.list_tools()
        print(f"[client] Available tools: {[t.name for t in tools]}")

        result = await client.call_tool("hello", {"name": "OAuth2 World"})
        print(f"\n[client] hello -> {result.content[0].text}")

        result = await client.call_tool("whoami", {})
        print(f"[client] whoami -> {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
