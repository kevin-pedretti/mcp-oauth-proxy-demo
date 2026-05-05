# mcp-oauth2-demo

A "hello world" [MCP](https://modelcontextprotocol.io) server built with [FastMCP](https://gofastmcp.com) that demonstrates the **OIDC proxy** authentication pattern.

Instead of validating tokens itself, the server acts as an OAuth proxy to an upstream OIDC provider (Auth0, Keycloak, Google, GitLab, etc.). MCP clients go through a standard browser-based OAuth flow — no manual token management required.

## How it works

```
MCP Client  ──► MCP Server (OIDC Proxy)  ──► Upstream OIDC Provider
                     │                               │
                     │  1. redirect to provider      │
                     │ ◄─────────────────────────────┤
                     │  2. exchange code for token   │
                     │ ──────────────────────────── ►│
                     │  3. issue FastMCP session JWT │
                     │ ◄─────────────────────────────┘
MCP Client  ◄── authenticated session
```

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — `brew install uv`

## Local testing (no external provider)

Pass `--dev` to run a fully self-contained in-memory OAuth provider. No credentials or `.env` needed.

### 1. Install dependencies

```bash
uv sync
```

### 2. Start the server in dev mode

```bash
uv run main.py --dev
```

### 3. Run the client

```bash
uv run client.py
```

On first run the client opens your browser, completes a local OAuth flow (no login required — the in-memory provider auto-approves), then calls all tools.

Tokens are kept in memory for the life of the process by default and discarded on exit, so each fresh `uv run client.py` re-does the browser flow. To persist tokens across runs, set `OAUTH_STORAGE_ENCRYPTION_KEY` in your `.env` — the client then writes Fernet-encrypted tokens to `~/.fastmcp/oauth-tokens/` and subsequent runs skip the browser flow until the cached token expires (see [Environment variables](#environment-variables)).

For headless / CI use or to skip the browser flow entirely, pass a pre-issued bearer token via the `TOKEN` env var: `TOKEN=<jwt> uv run client.py`. See also [`get_gitlab_token.py`](#option-b--get_gitlab_tokenpy-public-client--pkce) for obtaining a GitLab id_token to use this way.

First run:

```
[client] Connected to http://localhost:8000/mcp
[client] Available tools: ['hello', 'whoami', 'set_user_value', 'get_user_value', 'set_session_value', 'get_session_value']

[client] hello -> Hello, OAuth2 World! (authenticated as: dev-user)
[client] whoami -> {"client_id": "...", "scopes": ["openid", "profile"], "subject": null, "issuer": null, ...}
[client] token expires in 1h0m0s

[client] --- Per-user state (persists across runs) ---
[client] visit_count from last run -> None
[client] stored user['visit_count'] = '1'

[client] --- Per-session state (lost when this script exits) ---
[client] stored session['session_counter'] = '1' (session abcd1234…)
[client] stored session['session_counter'] = '2' (session abcd1234…)
[client] stored session['session_counter'] = '3' (session abcd1234…)

[client] Done.
```

Second run (per-user `visit_count` persisted; `session_counter` resets to 1):

```
[client] hello -> Hello, OAuth2 World! (authenticated as: dev-user)
...

[client] --- Per-user state (persists across runs) ---
[client] visit_count from last run -> 1
[client] stored user['visit_count'] = '2'

[client] --- Per-session state (lost when this script exits) ---
[client] stored session['session_counter'] = '1' (session efgh5678…)
[client] stored session['session_counter'] = '2' (session efgh5678…)
[client] stored session['session_counter'] = '3' (session efgh5678…)

[client] Done.
```

> **Note:** With `--dev`, `subject` and `issuer` are `null` in `whoami` — the in-memory provider issues opaque tokens, not JWTs, so there are no identity claims. Per-user state is keyed by `"dev-user"` in this mode.

## Connecting to a real OIDC provider

### 1. Register an OAuth application

In your provider's developer console, create a new OAuth application (called "Regular Web App", "Web Application", etc. depending on the provider) and set the callback URL to:

```
http://localhost:8000/auth/callback
```

For a production deployment, use your public server URL instead.

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your provider's values:

```bash
cp .env.example .env
```

```bash
# .env
OIDC_CONFIG_URL=https://your-provider.example.com/.well-known/openid-configuration
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret

# Required by some providers (e.g. Auth0); omit for others (Keycloak, Google, GitLab)
# OIDC_AUDIENCE=https://your-api-identifier

BASE_URL=http://localhost:8000
```

### 3. Start the server

```bash
uv run main.py
```

### 4. Run the client

```bash
uv run client.py
```

The client opens your browser to the provider's login page. After authenticating, the OAuth flow completes automatically and the client calls the tools.

---

### Provider-specific notes

#### Auth0

1. Create a **Regular Web Application** in the Auth0 dashboard
2. Under **Settings**, add `http://localhost:8000/auth/callback` to **Allowed Callback URLs**
3. Create an **API** in Auth0 and note its **Identifier** — this is your `OIDC_AUDIENCE`

```bash
OIDC_CONFIG_URL=https://YOUR_TENANT.auth0.com/.well-known/openid-configuration
OIDC_CLIENT_ID=<Client ID>
OIDC_CLIENT_SECRET=<Client Secret>
OIDC_AUDIENCE=https://your-api-identifier
BASE_URL=http://localhost:8000
```

#### Keycloak

1. Create a **Client** in your realm with **Client authentication** enabled
2. Add `http://localhost:8000/auth/callback` to **Valid redirect URIs**

```bash
OIDC_CONFIG_URL=https://keycloak.example.com/realms/YOUR_REALM/.well-known/openid-configuration
OIDC_CLIENT_ID=<Client ID>
OIDC_CLIENT_SECRET=<Client Secret>
BASE_URL=http://localhost:8000
```

#### GitLab

##### Option A — MCP server proxy (confidential client)

1. Go to **User Settings → Applications** (or **Admin → Applications** for an instance-wide app)
2. Enable scopes: `openid profile email`
3. Set redirect URI to `http://localhost:8000/auth/callback`
4. Leave **Confidential** checked

```bash
OIDC_CONFIG_URL=https://gitlab.example.com/.well-known/openid-configuration
OIDC_CLIENT_ID=<Application ID>
OIDC_CLIENT_SECRET=<Secret>
BASE_URL=http://localhost:8000
# GitLab issues opaque access tokens — verify the id_token JWT instead
OIDC_VERIFY_ID_TOKEN=true
```

##### Option B — `get_gitlab_token.py` (public client + PKCE)

Use this when you want to obtain a GitLab OIDC ID token directly and pass it to the client, without going through the MCP server proxy.

1. Go to **User Settings → Applications**
2. Enable scopes: `openid profile email`
3. Set redirect URI to `http://localhost:9999/callback`
4. Uncheck **Confidential** — no secret is issued or required

Set only two environment variables:

```bash
GITLAB_URL=https://gitlab.example.com
GITLAB_CLIENT_ID=<Application ID>
```

Then obtain the token and pass it to the client:

```bash
TOKEN=$(uv run get_gitlab_token.py) uv run client.py
```

The script uses the Authorization Code flow with PKCE (S256). No `GITLAB_CLIENT_SECRET` is needed.

---

## Tools

| Tool | Required scope | Description |
|------|---------------|-------------|
| `hello(name)` | `openid` | Returns a greeting including the authenticated subject |
| `whoami()` | `profile` | Returns identity info from the session token. With `--debug-claims`, also includes a `_debug_claims` field containing all raw decoded token claims. |
| `set_user_value(key, value)` | `openid` | Store a key/value pair for the current user (see [Per-user state](#per-user-state)) |
| `get_user_value(key)` | `openid` | Retrieve a stored value for the current user |
| `set_session_value(key, value)` | `openid` | Store a key/value pair for the current session (see [Per-session state](#per-session-state)) |
| `get_session_value(key)` | `openid` | Retrieve a stored value for the current session |

## State management

This server demonstrates two patterns for maintaining state across tool calls.

### Per-user state

`set_user_value` / `get_user_value` store data in a local SQLite database (`server_state.db`) keyed by the `sub` claim from the authenticated JWT. This means:

- **Persistent** — values survive server restarts.
- **Identity-scoped** — the same user reconnecting from a different client or in a new session sees the same values.
- **Isolated** — different users never see each other's values.

The database path can be overridden with the `STATE_DB_PATH` environment variable. In `--dev` mode, where the in-memory provider issues opaque tokens with no `sub` claim, the key falls back to the fixed string `"dev-user"`.

### Per-session state

`set_session_value` / `get_session_value` store data in memory keyed by the MCP session ID (the `mcp-session-id` HTTP header). All tool calls within a single `async with Client(...) as client:` block share the same session ID and therefore share this state. This means:

- **Ephemeral** — values are lost when the client disconnects or the server restarts.
- **Connection-scoped** — two separate script runs, even as the same user, get independent session state.

Use per-user state when data should follow the user across reconnects (e.g. preferences, history). Use per-session state for transient context that only makes sense within a single interaction (e.g. conversation state, request counters).

## Server flags

| Flag | Description |
|------|-------------|
| `--dev` | Use the in-memory OAuth provider. No external OIDC provider or `.env` needed. |
| `--debug-claims` | Append a `_debug_claims` field to `whoami()` responses containing all raw decoded token claims. Useful for inspecting what your OIDC provider actually issues. Do not use in production. |
| `--host HOST` | Bind address (default: `127.0.0.1`; use `0.0.0.0` in containers). |
| `--port PORT` | Port to listen on (default: `8000`). |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OIDC_CONFIG_URL` | _(required)_ | Provider's OpenID configuration URL |
| `OIDC_CLIENT_ID` | _(required)_ | OAuth application client ID |
| `OIDC_CLIENT_SECRET` | _(required)_ | OAuth application client secret |
| `OIDC_AUDIENCE` | _(unset)_ | API audience identifier (required by some providers, e.g. Auth0) |
| `OIDC_VERIFY_ID_TOKEN` | `false` | Set to `true` to verify the `id_token` instead of the `access_token`. Use when the provider issues opaque access tokens (e.g. GitLab). |
| `BASE_URL` | `http://localhost:{PORT}` | Public URL of this server (used in OAuth redirect URIs) |
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8000` | Server port |
| `STATE_DB_PATH` | `<server-dir>/server_state.db` | Path to the SQLite database used for per-user state. Defaults to `server_state.db` next to `main.py` so it's predictable regardless of the working directory the server is launched from. |
| `OAUTH_STORAGE_ENCRYPTION_KEY` | _(unset)_ | Fernet key for encrypting OAuth tokens stored at `~/.fastmcp/oauth-tokens/`. If unset, the client falls back to in-memory token storage — tokens are kept for the life of the process and discarded on exit, with nothing written to disk. Generate a persistent key with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `TOKEN` _(client only)_ | _(unset)_ | Pre-issued bearer token for the client. When set, `client.py` skips the browser-based OAuth flow and the on-disk/in-memory token cache, sending the value as `Authorization: Bearer <TOKEN>` directly. Useful for headless / CI runs and for pairing with `get_gitlab_token.py` (`TOKEN=$(uv run get_gitlab_token.py) uv run client.py`). |
| `SERVER_URL` _(client only)_ | `http://localhost:8000/mcp` | URL the client connects to. |

## Docker

Build and run using the provided Dockerfile:

```bash
docker build -t mcp-oauth2-demo .

# Dev mode (no provider needed)
docker run -p 8000:8000 mcp-oauth2-demo uv run main.py --dev --host 0.0.0.0

# Real OIDC provider
docker run -p 8000:8000 \
  -e OIDC_CONFIG_URL=https://YOUR_TENANT.auth0.com/.well-known/openid-configuration \
  -e OIDC_CLIENT_ID=your-client-id \
  -e OIDC_CLIENT_SECRET=your-client-secret \
  -e BASE_URL=https://your-public-server.example.com \
  mcp-oauth2-demo
```

When running behind a proxy or in a container, set `BASE_URL` to the public-facing URL so OAuth redirect URIs are correct.

## Helm (OpenShift)

A Helm chart is provided in the `helm/` directory. It deploys a Deployment, Service, and OpenShift Route with TLS edge termination.

```bash
helm install my-release helm/ \
  --set auth.oidcConfigUrl=https://YOUR_TENANT.auth0.com/.well-known/openid-configuration \
  --set auth.oidcClientId=your-client-id \
  --set auth.oidcClientSecret=your-client-secret \
  --set auth.baseUrl=https://your-route.apps.example.com
```

The chart is compatible with OpenShift's `restricted-v2` SCC — it sets `runAsNonRoot: true` and drops all Linux capabilities without pinning a UID, allowing OpenShift to assign one at runtime.

## Running the tests

```bash
uv run pytest test_integration.py -v
```

## Project structure

```
.
├── main.py             # FastMCP server with OIDCProxy auth, per-user (SQLite) and per-session state (--dev flag for local testing)
├── client.py           # Demo client using browser-based OAuth flow
├── get_gitlab_token.py # Utility: obtain a GitLab OIDC ID token directly via public client + PKCE (no secret required)
├── decode_token.py     # Utility: decode a JWT and print its header and claims
├── pyproject.toml      # Project dependencies (uv)
├── Dockerfile          # UBI9-based container image
├── helm/               # Helm chart for OpenShift deployment
└── .env.example        # Environment variable reference
```

## FastMCP patch

`fastmcp-3.2.4.patch` fixes a bug in FastMCP 3.2.4 where `OIDC_VERIFY_ID_TOKEN=true` stops working after the id_token expires (typically 2 minutes for GitLab), even though the access token and refresh token are still valid. The transparent token refresh never fires because it checks the access token expiry instead of the id_token expiry. A PR has been filed upstream against [PrefectHQ/fastmcp](https://github.com/PrefectHQ/fastmcp).

After `uv sync`, re-apply the patch with:

```bash
patch -p1 -d .venv/lib/python3.12/site-packages < fastmcp-3.2.4.patch
```
