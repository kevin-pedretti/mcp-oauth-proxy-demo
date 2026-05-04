"""Integration test: boots the server in dev mode and exercises the main tool round-trip."""

import json

import pytest_asyncio
from fastmcp import Client
from fastmcp.utilities.http import find_available_port
from fastmcp.utilities.tests import HeadlessOAuth, run_server_async
from key_value.aio.stores.memory import MemoryStore

import main as server_module


@pytest_asyncio.fixture
async def dev_server(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(server_module, "_dev_mode", True)
    server_module._init_db()

    port = find_available_port()
    server_module.mcp.auth = server_module.build_auth(
        dev=True, base_url=f"http://127.0.0.1:{port}"
    )

    async with run_server_async(server_module.mcp, port=port) as url:
        yield url


async def test_hello_whoami_set_get_state(dev_server):
    auth = HeadlessOAuth(dev_server, token_storage=MemoryStore())
    async with Client(dev_server, auth=auth) as client:
        result = await client.call_tool("hello", {"name": "World"})
        assert "Hello, World!" in result.content[0].text

        result = await client.call_tool("whoami", {})
        data = json.loads(result.content[0].text)
        assert "openid" in data["scopes"]
        assert "profile" in data["scopes"]

        await client.call_tool("set_user_value", {"key": "visit_count", "value": "42"})
        result = await client.call_tool("get_user_value", {"key": "visit_count"})
        assert result.content[0].text == "42"

        await client.call_tool("set_session_value", {"key": "session_counter", "value": "7"})
        result = await client.call_tool("get_session_value", {"key": "session_counter"})
        assert result.content[0].text == "7"
