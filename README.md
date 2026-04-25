# mcp-oauth2-demo

A "hello world" [MCP](https://modelcontextprotocol.io) server built with [FastMCP](https://gofastmcp.com) that demonstrates the **OIDC proxy** authentication pattern.

Instead of validating tokens itself, the server acts as an OAuth proxy to an upstream OIDC provider (Auth0, Keycloak, Google, GitLab, etc.). MCP clients go through a standard browser-based OAuth flow — no manual token management required.

## How it works

```
MCP Client  ──► MCP Server (OIDC Proxy)  ──► Upstream OIDC Provider
                     │                              │
                     │  1. redirect to provider     │
                     │ ◄────────────────────────────┤
                     │  2. exchange code for token  │
                     │ ──────────────────────────── ►│
                     │  3. issue FastMCP session JWT │
                     │ ◄────────────────────────────┘
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

On first run the client opens your browser, completes a local OAuth flow (no login required — the in-memory provider auto-approves), then calls both tools:

```
[client] Connected to http://localhost:8000/mcp
[client] Available tools: ['hello', 'whoami']

[client] hello -> Hello, OAuth2 World! (authenticated as: unknown)
[client] whoami -> {"client_id": "...", "scopes": ["openid", "profile"], ...}
```

> **Note:** With `--dev`, `subject` and `issuer` are `null` in `whoami` — the in-memory provider issues opaque tokens, not JWTs, so there are no identity claims.

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

1. Go to **User Settings → Applications** (or **Admin → Applications** for an instance-wide app)
2. Enable scopes: `openid profile email`
3. Set redirect URI to `http://localhost:8000/auth/callback`

```bash
OIDC_CONFIG_URL=https://gitlab.example.com/.well-known/openid-configuration
OIDC_CLIENT_ID=<Application ID>
OIDC_CLIENT_SECRET=<Secret>
BASE_URL=http://localhost:8000
# GitLab issues opaque access tokens — verify the id_token JWT instead
OIDC_VERIFY_ID_TOKEN=true
```

---

## Tools

| Tool | Required scope | Description |
|------|---------------|-------------|
| `hello(name)` | `openid` | Returns a greeting including the authenticated subject |
| `whoami()` | `profile` | Returns identity info from the session token |

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

## Project structure

```
.
├── main.py             # FastMCP server with OIDCProxy auth (--dev flag for local testing)
├── client.py           # Demo client using browser-based OAuth flow
├── get_gitlab_token.py # Utility: obtain a GitLab OIDC token directly (standalone use)
├── decode_token.py     # Utility: decode a JWT and print its header and claims
├── pyproject.toml      # Project dependencies (uv)
├── Dockerfile          # UBI9-based container image
├── helm/               # Helm chart for OpenShift deployment
└── .env.example        # Environment variable reference
```
