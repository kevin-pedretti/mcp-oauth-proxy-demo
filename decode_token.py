"""Decode and display a JWT without verifying the signature.

Usage:
    python decode_token.py <token>
    python decode_token.py                        # reads from TOKEN env var
    TOKEN=$(uv run get_gitlab_token.py) python decode_token.py
"""

import argparse
import json
import os
import sys

import jwt


def main():
    parser = argparse.ArgumentParser(description="Decode a JWT and print its claims")
    parser.add_argument("token", nargs="?", help="JWT string (falls back to TOKEN env var)")
    args = parser.parse_args()

    token = args.token or os.environ.get("TOKEN")
    if not token:
        print("Error: provide a token as an argument or via the TOKEN env var", file=sys.stderr)
        sys.exit(1)

    header = jwt.get_unverified_header(token)
    claims = jwt.decode(token, options={"verify_signature": False})

    # Warn loudly so nobody mistakes the decoded claims for trustworthy
    # claims. Goes to stderr so it stays visible even if stdout is
    # redirected to a file.
    print(
        "WARNING: signature NOT verified — these claims are decoded blindly\n"
        "         and must not be trusted for any authentication or\n"
        "         authorization decision.\n",
        file=sys.stderr,
    )

    print("=== Header ===")
    print(json.dumps(header, indent=2))
    print("\n=== Claims ===")
    print(json.dumps(claims, indent=2))


if __name__ == "__main__":
    main()
