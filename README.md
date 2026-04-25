# mcp-oauth2-demo

A "hello world" [MCP](https://modelcontextprotocol.io) server built with [FastMCP](https://gofastmcp.com) that requires OAuth2/OIDC bearer token authentication on every request.

Works out of the box with a local HMAC shared secret. Drop in a `JWKS_URI` to connect to any real OIDC provider (Auth0, Keycloak, Google, etc.).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) — `brew install uv`

## Quickstart

### 1. Create a virtual environment and install dependencies

```bash
uv venv
source .venv/bin/activate
uv sync
```

### 2. Start the server

```bash
python main.py

# bind to all interfaces (e.g. for Docker or remote access)
python main.py --host 0.0.0.0

# custom port
python main.py --port 9000
```

The server listens on `http://127.0.0.1:8000/mcp` by default. Requests without a valid bearer token receive `401 Unauthorized`.

### 3. Run the demo client

```bash
python client.py
```

The client auto-generates a local dev token, connects to the server, and calls both tools:

```
[client] Generated local dev token: eyJhbGciOiJIUzI1NiIsIn...

[client] Connected to http://localhost:8000/mcp
[client] Available tools: ['hello', 'whoami']

[client] hello -> Hello, OAuth2 World! (authenticated as: test-user)
[client] whoami -> {"subject":"test-user","issuer":"http://localhost:8000",...}
```

## Tools

| Tool | Description |
|------|-------------|
| `hello(name)` | Returns a greeting that includes the token's `sub` claim |
| `whoami()` | Returns all relevant claims from the bearer token |

## Generating tokens manually

```bash
# Default (subject=test-user, scope="read write", TTL=1h)
python generate_token.py

# Custom
python generate_token.py --subject alice --scope "read" --ttl 7200
```

Decode a token to inspect its claims:

```bash
python decode_token.py <token>

# or pass via TOKEN env var
TOKEN=$(python generate_token.py) python decode_token.py
```

Pass the token to the client:

```bash
TOKEN=$(python generate_token.py) python client.py
```

Or use it with `curl`:

```bash
TOKEN=$(python generate_token.py)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/mcp
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | `dev-secret-change-in-prod-minimum-32b` | HMAC shared secret (used when `JWKS_URI` is not set) |
| `JWKS_URI` | _(unset)_ | JWKS endpoint from your OIDC provider; overrides `JWT_SECRET` |
| `JWT_ISSUER` | `http://localhost:8000` | Expected `iss` claim in tokens |
| `JWT_AUDIENCE` | `mcp-server` | Expected `aud` claim in tokens |
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8000` | Server port |

Copy `.env.example` to `.env` and the server will pick it up automatically.

## Using a real OIDC provider

Set `JWKS_URI` to your provider's JWKS endpoint and update the issuer/audience to match:

```bash
# Auth0
JWKS_URI=https://YOUR_DOMAIN.auth0.com/.well-known/jwks.json \
JWT_ISSUER=https://YOUR_DOMAIN.auth0.com/ \
JWT_AUDIENCE=https://your-api-identifier \
python main.py

# Keycloak
JWKS_URI=https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs \
JWT_ISSUER=https://keycloak.example.com/realms/myrealm \
JWT_AUDIENCE=account \
python main.py
```

Tokens must be issued by the configured provider and signed with the keys from the JWKS endpoint. The server validates `iss`, `aud`, and `exp` on every request.

## Using GitLab as the OIDC provider

`get_gitlab_token.py` performs the OAuth2 authorization code flow against a GitLab instance and prints the resulting ID token (a GitLab-signed JWT) so it can be passed directly to the client.

### 1. Create a GitLab OAuth application

Go to **User Settings → Applications** (or **Admin → Applications** for an instance-wide app) and create a new application:

- **Scopes:** `openid profile email`
- **Redirect URI:** `http://localhost:9999/callback`

### 2. Configure environment variables

Add to your `.env` (see `.env.example`):

```bash
# GitLab token acquisition
GITLAB_URL=https://gitlab.example.com
GITLAB_CLIENT_ID=<Application ID>
GITLAB_CLIENT_SECRET=<Secret>

# Point the MCP server at GitLab's JWKS
JWKS_URI=https://gitlab.example.com/oauth/discovery/keys
JWT_ISSUER=https://gitlab.example.com
JWT_AUDIENCE=<Application ID>
```

### 3. Get a token and run the client

```bash
TOKEN=$(uv run get_gitlab_token.py) SERVER_URL=https://your-mcp-host/mcp uv run client.py
```

`get_gitlab_token.py` opens a browser tab for GitLab login, catches the redirect on `localhost:9999`, exchanges the authorization code for tokens, and prints only the `id_token` — so the `$()` capture works cleanly.

## Docker

Build and run using the provided UBI9-based Dockerfile:

```bash
docker build -t mcp-oauth2-demo .

# Run with default dev secret (localhost only)
docker run -p 8000:8000 mcp-oauth2-demo

# Run with a real OIDC provider
docker run -p 8000:8000 \
  -e JWKS_URI=https://YOUR_DOMAIN.auth0.com/.well-known/jwks.json \
  -e JWT_ISSUER=https://YOUR_DOMAIN.auth0.com/ \
  -e JWT_AUDIENCE=https://your-api-identifier \
  mcp-oauth2-demo
```

The container binds to `0.0.0.0:8000` by default (required to be reachable from outside the container). Set `JWT_SECRET` to a strong random value in production.

## Helm (OpenShift)

A Helm chart is provided in the `helm/` directory. It deploys a Deployment, Service, and OpenShift Route with TLS edge termination.

```bash
# Install with default dev secret
helm install my-release helm/

# Install pointing at a real OIDC provider
helm install my-release helm/ \
  --set auth.jwksUri=https://YOUR_DOMAIN.auth0.com/.well-known/jwks.json \
  --set auth.jwtIssuer=https://YOUR_DOMAIN.auth0.com/ \
  --set auth.jwtAudience=https://your-api-identifier

# Use a pre-existing Secret for JWT_SECRET
helm install my-release helm/ \
  --set auth.existingSecret=my-secret \
  --set auth.existingSecretKey=jwt-secret
```

The chart is compatible with OpenShift's `restricted-v2` SCC — it sets `runAsNonRoot: true` and drops all Linux capabilities without pinning a UID, allowing OpenShift to assign one at runtime.

## Project structure

```
.
├── main.py             # FastMCP server with JWTVerifier auth
├── generate_token.py   # Mint local HMAC JWTs for testing
├── decode_token.py     # Decode a JWT and print its header and claims
├── client.py           # Demo client using BearerAuth
├── get_gitlab_token.py # Obtain a GitLab OIDC ID token via browser OAuth2 flow
├── pyproject.toml      # Project dependencies (uv)
├── Dockerfile          # UBI9-based container image
├── helm/               # Helm chart for OpenShift deployment
└── .env.example        # Environment variable reference
```
