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
"""

import argparse
import os

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token


def require_scope(scope: str) -> None:
    token = get_access_token()
    if token is None:
        raise PermissionError("No authenticated token")
    if scope not in (token.scopes or []):
        raise PermissionError(f"Token missing required scope: '{scope}'")


mcp = FastMCP(name="Hello World MCP")


@mcp.tool
def hello(name: str = "World") -> str:
    """Say hello. Requires the 'openid' scope."""
    require_scope("openid")
    token = get_access_token()
    subject = token.claims.get("sub", "unknown") if token else "unknown"
    return f"Hello, {name}! (authenticated as: {subject})"


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

    base_url = os.environ.get("BASE_URL", f"http://localhost:{args.port}")
    mcp.auth = build_auth(dev=args.dev, base_url=base_url)

    mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
