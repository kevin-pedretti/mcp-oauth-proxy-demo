FROM registry.access.redhat.com/ubi9/python-312

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install runtime deps from the lockfile for a fully reproducible image.
# --frozen fails fast if pyproject.toml and uv.lock are out of sync.
# --no-dev skips dev/client tooling not needed at runtime.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy only the server — dev tools (client, decode_token, get_gitlab_token) are not needed at runtime
COPY main.py ./

# In a container the server must bind to all interfaces to be reachable from outside
ENV HOST=0.0.0.0

EXPOSE 8000

ENTRYPOINT ["/app/.venv/bin/python", "main.py"]
