"""Obtain a GitLab OIDC ID token via the authorization code flow (public client + PKCE).

The printed ID token is a JWT signed by GitLab's JWKS and can be passed
directly to the MCP client:

    TOKEN=$(uv run get_gitlab_token.py) uv run client.py

Prerequisites:
    1. Create an OAuth2 application in GitLab:
         User Settings → Applications  (or Admin → Applications for instance-wide)
         Scopes:        openid profile email
         Redirect URI:  http://localhost:9999/callback
         Check "Confidential" OFF  (public client — no secret required)

    2. Set the following environment variables (or add them to .env):
         GITLAB_URL        - e.g. https://gitlab.example.com
         GITLAB_CLIENT_ID  - Application ID from step 1

    3. Configure the MCP server to validate against GitLab's JWKS:
         JWKS_URI=https://<your-gitlab>/oauth/discovery/keys
         JWT_ISSUER=https://<your-gitlab>
         JWT_AUDIENCE=<your-client-id>
"""

import base64
import hashlib
import http.server
import os
import platform
import secrets
import subprocess
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

GITLAB_URL = os.environ["GITLAB_URL"].rstrip("/")
CLIENT_ID = os.environ["GITLAB_CLIENT_ID"]
REDIRECT_URI = "http://localhost:9999/callback"
SCOPE = "openid profile email"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge

_code: dict[str, str] = {}


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" not in qs:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing 'code' parameter.")
            return
        _code["value"] = qs["code"][0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Authentication successful - you can close this tab.")

    def log_message(self, *_):
        pass


def main():
    code_verifier, code_challenge = _pkce_pair()

    auth_url = (
        f"{GITLAB_URL}/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(SCOPE)}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )

    browser = os.environ.get("BROWSER")
    print(f"[get_gitlab_token] Opening browser for GitLab login...", flush=True)
    if browser and platform.system() == "Darwin":
        subprocess.Popen(["open", "-a", browser, auth_url])
    else:
        webbrowser.open(auth_url)

    httpd = http.server.HTTPServer(("", 9999), _CallbackHandler)
    httpd.handle_request()

    code = _code.get("value")
    if not code:
        raise RuntimeError("No authorization code received.")

    resp = requests.post(
        f"{GITLAB_URL}/oauth/token",
        data={
            "client_id": CLIENT_ID,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=10,
    )
    resp.raise_for_status()
    tokens = resp.json()

    id_token = tokens.get("id_token")
    if not id_token:
        raise RuntimeError(f"No id_token in response: {tokens}")

    # Print only the token so callers can capture it with $()
    print(id_token)


if __name__ == "__main__":
    main()
