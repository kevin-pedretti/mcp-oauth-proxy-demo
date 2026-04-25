"""Generate a local JWT for testing the MCP server.

Usage:
    uv run generate_token.py
    uv run generate_token.py --subject alice --scope "read write" --ttl 3600
"""

import argparse
import os
import time

import jwt

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod-minimum-32b")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "http://localhost:8000")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "mcp-server")


def generate(subject: str, scope: str, ttl: int) -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + ttl,
        "scope": scope,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def main():
    parser = argparse.ArgumentParser(description="Generate a test JWT")
    parser.add_argument("--subject", default="test-user", help="Token subject (user id)")
    parser.add_argument("--scope", default="read write profile", help="Space-separated scopes")
    parser.add_argument("--ttl", type=int, default=3600, help="Lifetime in seconds")
    args = parser.parse_args()

    token = generate(args.subject, args.scope, args.ttl)
    print(token)


if __name__ == "__main__":
    main()
