"""Hello World MCP server with OAuth2/OIDC authentication.

By default uses a local HMAC shared secret for JWT verification (no external
provider required). To use a real OIDC provider, set JWKS_URI instead of
JWT_SECRET.

Environment variables:
    JWT_SECRET   - Shared HMAC secret (default: "dev-secret-change-in-prod")
    JWKS_URI     - JWKS endpoint URL from your OIDC provider (overrides JWT_SECRET)
    JWT_ISSUER   - Expected token issuer (default: "http://localhost:8000")
    JWT_AUDIENCE - Expected token audience (default: "mcp-server")
    HOST         - Server host (default: "127.0.0.1")
    PORT         - Server port (default: 8000)
"""

import argparse
import os

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod-minimum-32b")
JWKS_URI = os.environ.get("JWKS_URI")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "http://localhost:8000")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "mcp-server")

if JWKS_URI:
    # Real OIDC provider (Auth0, Keycloak, Google, etc.)
    verifier = JWTVerifier(
        jwks_uri=JWKS_URI,
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
    )
else:
    # Local HMAC secret — great for development and demos
    verifier = JWTVerifier(
        public_key=JWT_SECRET,
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
        algorithm="HS256",
    )

mcp = FastMCP(name="Hello World MCP", auth=verifier)


def require_scope(scope: str) -> None:
    token = get_access_token()
    if token is None:
        raise PermissionError("No authenticated token")
    granted = token.claims.get("scope", "").split()
    if scope not in granted:
        raise PermissionError(f"Token missing required scope: '{scope}'")


@mcp.tool
def hello(name: str = "World") -> str:
    """Say hello. Requires the 'read' scope."""
    require_scope("read")
    token = get_access_token()
    subject = token.claims.get("sub", "unknown") if token else "unknown"
    return f"Hello, {name}! (authenticated as: {subject})"


@mcp.tool
def whoami() -> dict:
    """Return claims from the authenticated bearer token. Requires the 'profile' scope."""
    require_scope("profile")
    token = get_access_token()
    return {
        "subject": token.claims.get("sub"),
        "issuer": token.claims.get("iss"),
        "audience": token.claims.get("aud"),
        "scopes": token.claims.get("scope", ""),
        "expires_at": token.claims.get("exp"),
    }


def main():
    parser = argparse.ArgumentParser(description="Hello World MCP server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")), help="Port (default: 8000)")
    args = parser.parse_args()

    mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
