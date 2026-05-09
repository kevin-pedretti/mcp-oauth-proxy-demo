"""Integration test: boots the server in dev mode and exercises the main tool round-trip."""

import asyncio
import io
import json
import sys
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.auth.oauth import ClientNotFoundError
from fastmcp.exceptions import AuthorizationError
from fastmcp.utilities.http import find_available_port
from fastmcp.utilities.tests import HeadlessOAuth, run_server_async
from key_value.aio.stores.memory import MemoryStore

import main as server_module
from client import OAuthOOB


@pytest_asyncio.fixture
async def dev_server(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setattr(server_module, "_dev_mode", True)
    server_module._init_db()

    port = find_available_port()
    server_module.mcp.auth = server_module.build_auth(
        dev=True, base_url=f"http://127.0.0.1:{port}"
    )
    # FastMCP creates _started once at construction time, binding it to the
    # event loop of the first test that runs. Subsequent tests each get a
    # fresh loop (pytest-asyncio default), so the stale Event raises
    # "bound to a different event loop". Reset it per-test here.
    server_module.mcp._started = asyncio.Event()

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


async def test_dev_fallback_identity(dev_server):
    """In dev mode the server falls back to 'dev-user' when the token has no sub claim."""
    auth = HeadlessOAuth(dev_server, token_storage=MemoryStore())
    async with Client(dev_server, auth=auth) as client:
        result = await client.call_tool("hello", {"name": "Test"})
        assert "dev-user" in result.content[0].text


def test_get_user_sub_no_sub_raises(monkeypatch):
    """get_user_sub() raises AuthorizationError when sub is absent and _dev_mode is False."""
    mock_token = MagicMock()
    mock_token.claims = {}
    monkeypatch.setattr(server_module, "get_access_token", lambda: mock_token)
    monkeypatch.setattr(server_module, "_dev_mode", False)

    with pytest.raises(AuthorizationError, match="no 'sub' claim"):
        server_module.get_user_sub()


# ---------------------------------------------------------------------------
# OAuthOOB — unit tests for redirect_handler and callback_handler branches
# ---------------------------------------------------------------------------

async def test_oob_callback_handler_parses_redirect_url(monkeypatch):
    """callback_handler extracts code and state from a pasted redirect URL."""
    oob = OAuthOOB("http://localhost:8000/mcp", token_storage=MemoryStore())
    monkeypatch.setattr(
        sys, "stdin",
        io.StringIO("http://localhost:8000/callback?code=abc123&state=xyz\n"),
    )
    code, state = await oob.callback_handler()
    assert code == "abc123"
    assert state == "xyz"


async def test_oob_callback_handler_missing_code_raises(monkeypatch):
    """callback_handler raises ValueError when the pasted URL has no code parameter."""
    oob = OAuthOOB("http://localhost:8000/mcp", token_storage=MemoryStore())
    monkeypatch.setattr(
        sys, "stdin",
        io.StringIO("http://localhost:8000/callback?state=xyz\n"),
    )
    with pytest.raises(ValueError, match="No 'code' parameter"):
        await oob.callback_handler()


async def test_oob_redirect_handler_raises_on_stale_client():
    """redirect_handler raises ClientNotFoundError when the server returns HTTP 400."""
    oob = OAuthOOB("http://localhost:8000/mcp", token_storage=MemoryStore())

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_httpx_client = AsyncMock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)

    @asynccontextmanager
    async def mock_factory():
        yield mock_httpx_client

    oob.httpx_client_factory = mock_factory

    with pytest.raises(ClientNotFoundError):
        await oob.redirect_handler("http://example.com/oauth/authorize?client_id=x")


async def test_oob_redirect_handler_raises_on_unexpected_status():
    """redirect_handler raises RuntimeError for status codes outside 200/302/303/307/308."""
    oob = OAuthOOB("http://localhost:8000/mcp", token_storage=MemoryStore())

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_httpx_client = AsyncMock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)

    @asynccontextmanager
    async def mock_factory():
        yield mock_httpx_client

    oob.httpx_client_factory = mock_factory

    with pytest.raises(RuntimeError, match="Unexpected authorization response: 500"):
        await oob.redirect_handler("http://example.com/oauth/authorize?client_id=x")


# ---------------------------------------------------------------------------
# OAuthOOB — integration test: full round-trip against the dev server
# ---------------------------------------------------------------------------

class _HeadlessOOB(OAuthOOB):
    """Drive OAuthOOB against the dev server without stdin interaction.

    Captures the authorization URL in redirect_handler and follows it
    in callback_handler (replicating what a user would do in a browser).
    The redirect_handler branches are covered by the unit tests above;
    this test exercises the complete OAuth flow with OAuthOOB as the
    auth provider.
    """

    def __init__(self, mcp_url: str, **kwargs: Any) -> None:
        super().__init__(mcp_url, **kwargs)
        self._auth_url: str | None = None

    async def redirect_handler(self, authorization_url: str) -> None:
        self._auth_url = authorization_url

    async def callback_handler(self) -> tuple[str, str | None]:
        assert self._auth_url is not None
        async with httpx.AsyncClient() as client:
            resp = await client.get(self._auth_url, follow_redirects=False)
        params = parse_qs(urlparse(resp.headers["location"]).query)
        return params["code"][0], params.get("state", [None])[0]


async def test_oob_flow(dev_server):
    """OAuthOOB completes a full OAuth round-trip and can call a tool."""
    auth = _HeadlessOOB(dev_server, token_storage=MemoryStore())
    async with Client(dev_server, auth=auth) as client:
        result = await client.call_tool("hello", {"name": "OOB"})
        assert "Hello, OOB!" in result.content[0].text
