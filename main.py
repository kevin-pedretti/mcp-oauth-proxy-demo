"""Hello World MCP server with OAuth2/OIDC authentication via the OIDC proxy flow.

The server delegates authentication to an upstream OIDC provider (Auth0, Google,
Keycloak, etc.). The proxy handles OAuth redirects and token validation — no manual
JWT secret management required.

Environment variables (required unless --dev is set):
    OIDC_CONFIG_URL    - Provider's OpenID configuration URL
                         (e.g. https://dev-xxx.auth0.com/.well-known/openid-configuration)
    OIDC_CLIENT_ID     - OAuth application client ID
    OIDC_CLIENT_SECRET    - OAuth application client secret
    OIDC_AUDIENCE         - API audience identifier (required by some providers like Auth0)
    OIDC_VERIFY_ID_TOKEN  - Set to "true" to verify the id_token instead of the access_token.
                            Use this when the provider issues opaque (non-JWT) access tokens
                            (e.g. GitLab). Default: false.
    BASE_URL              - Public URL of this MCP server (default: http://localhost:8000)
    HOST               - Server host (default: 127.0.0.1)
    PORT               - Server port (default: 8000)
    STATE_DB_PATH      - Path to SQLite database for per-user state (default: server_state.db)
"""

import argparse
import asyncio
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from fastmcp.exceptions import AuthorizationError
from fastmcp.server.dependencies import get_access_token

load_dotenv()


# ---------------------------------------------------------------------------
# Per-user state — SQLite-backed, keyed by JWT sub claim.
# Values are shared across all sessions for the same identity and survive
# server restarts.
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    # Anchor the default to this file's directory, not cwd. Containers and
    # systemd units can run with surprising working directories; resolving
    # against __file__ keeps the DB next to the server module regardless.
    default = Path(__file__).resolve().parent / "server_state.db"
    return Path(os.environ.get("STATE_DB_PATH") or default)


def _connect() -> sqlite3.Connection:
    """Open a SQLite connection with sane concurrency settings.

    busy_timeout is per-connection — it must be set on every new connection,
    not just at init — so all DB access funnels through this helper.
    """
    conn = sqlite3.connect(_db_path())
    # Wait up to 5 s for a lock instead of failing immediately with SQLITE_BUSY.
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _init_db() -> None:
    with _connect() as conn:
        # WAL mode lets readers and a single writer run concurrently — readers
        # no longer block on a writer, and vice versa. The setting is persistent
        # (recorded in the database header), so this only needs to be set once.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_state (
                sub   TEXT NOT NULL,
                key   TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (sub, key)
            )
        """)


def _db_set(sub: str, key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO user_state (sub, key, value) VALUES (?, ?, ?)",
            (sub, key, value),
        )


def _db_get(sub: str, key: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM user_state WHERE sub = ? AND key = ?",
            (sub, key),
        ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_dev_mode: bool = False


def require_scope(scope: str) -> None:
    # AuthorizationError is FastMCP's canonical exception for auth failures.
    # The framework catches it in tool listings/lookups and surfaces a
    # structured error to the client — using PermissionError leaks as a
    # generic 500 instead.
    token = get_access_token()
    if token is None:
        raise AuthorizationError("No authenticated token")
    if scope not in (token.scopes or []):
        raise AuthorizationError(f"Token missing required scope: '{scope}'")


def get_user_sub() -> str:
    """Return the subject identifier for the current user.

    In dev mode, falls back to a fixed "dev-user" constant when sub is absent
    (the in-memory provider issues opaque tokens with no sub claim, and its
    client_id changes on every restart as clients re-register).  Outside dev
    mode the fallback is disabled: client_id identifies the OAuth application,
    not the individual user, so using it as a per-user key would let every
    user of the same app share a state bucket.
    """
    token = get_access_token()
    sub = token.claims.get("sub") if token else None
    if sub:
        return sub
    if _dev_mode:
        return "dev-user"
    # Same reasoning as require_scope: AuthorizationError surfaces a
    # structured error to the client. ValueError would leak as a generic
    # 500 with no actionable message.
    raise AuthorizationError(
        "Token has no 'sub' claim — cannot key per-user state. "
        "Ensure your OIDC provider issues JWT tokens with a subject claim."
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP(name="Hello World MCP")


@mcp.tool
def hello(name: str = "World") -> str:
    """Say hello. Requires the 'openid' scope."""
    require_scope("openid")
    return f"Hello, {name}! (authenticated as: {get_user_sub()})"


@mcp.tool
def whoami() -> dict:
    """Return claims from the authenticated bearer token. Requires the 'profile' scope."""
    require_scope("profile")
    token = get_access_token()
    return {
        "client_id": token.client_id,
        "scopes": token.scopes,
        "expires_at": token.expires_at,
        # JWT-only fields (None when using InMemoryOAuthProvider)
        "subject": token.claims.get("sub"),
        "issuer": token.claims.get("iss"),
    }


@mcp.tool
async def set_user_value(key: str, value: str) -> str:
    """Store a value for the current user (persists across sessions and server restarts).
    Requires the 'openid' scope."""
    require_scope("openid")
    sub = get_user_sub()
    await asyncio.to_thread(_db_set, sub, key, value)
    return f"stored user[{key!r}] = {value!r}"


@mcp.tool
async def get_user_value(key: str) -> str | None:
    """Retrieve a stored value for the current user. Returns null if not set.
    Requires the 'openid' scope."""
    require_scope("openid")
    sub = get_user_sub()
    return await asyncio.to_thread(_db_get, sub, key)


@mcp.tool
async def set_session_value(key: str, value: str, ctx: Context) -> str:
    """Store a value for the current session (lost when client disconnects).
    Requires the 'openid' scope."""
    require_scope("openid")
    await ctx.set_state(key, value)
    return f"stored session[{key!r}] = {value!r} (session {ctx.session_id[:8]}…)"


@mcp.tool
async def get_session_value(key: str, ctx: Context) -> str | None:
    """Retrieve a stored value for the current session. Returns null if not set.
    Requires the 'openid' scope."""
    require_scope("openid")
    return await ctx.get_state(key)


# ---------------------------------------------------------------------------
# Auth / startup
# ---------------------------------------------------------------------------

def build_auth(dev: bool, base_url: str):
    if dev:
        from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider
        from mcp.server.auth.settings import ClientRegistrationOptions
        return InMemoryOAuthProvider(
            base_url=base_url,
            required_scopes=["openid", "profile"],
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["openid", "profile"],
            ),
        )

    from fastmcp.server.auth.oidc_proxy import OIDCProxy
    missing = [v for v in ("OIDC_CONFIG_URL", "OIDC_CLIENT_ID") if not os.environ.get(v)]
    if missing:
        raise SystemExit(
            f"error: missing required environment variable(s): {', '.join(missing)}\n"
            "Set them to your OIDC provider's values, or pass --dev to use the in-memory provider."
        )
    verify_id_token = os.environ.get("OIDC_VERIFY_ID_TOKEN", "").lower() in ("1", "true")
    return OIDCProxy(
        config_url=os.environ["OIDC_CONFIG_URL"],
        client_id=os.environ["OIDC_CLIENT_ID"],
        client_secret=os.environ.get("OIDC_CLIENT_SECRET"),
        audience=os.environ.get("OIDC_AUDIENCE"),
        base_url=base_url,
        verify_id_token=verify_id_token,
    )


def main():
    parser = argparse.ArgumentParser(description="Hello World MCP server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Port (default: 8000)")
    parser.add_argument("--dev", action="store_true", help="Use in-memory OAuth provider (no external OIDC provider required)")
    args = parser.parse_args()

    global _dev_mode
    _dev_mode = args.dev

    _init_db()

    base_url = os.environ.get("BASE_URL", f"http://localhost:{args.port}")
    mcp.auth = build_auth(dev=args.dev, base_url=base_url)

    try:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
