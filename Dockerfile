FROM registry.access.redhat.com/ubi9/python-312

WORKDIR /app

# Install uv for deterministic, fast deps install. Previously this
# layer hand-rolled `pip install fastmcp "PyJWT[crypto]"`, which had
# drifted from pyproject.toml: PyJWT is no longer a project dep (it
# was only used by the deleted generate_token.py), and
# py-key-value-aio[disk] — which IS a declared dep — was missing.
# Installing from pyproject.toml keeps the image in lockstep with the
# project's declared dependencies.
RUN pip install --no-cache-dir uv

# Install only the runtime [project.dependencies] from pyproject.toml.
# `uv pip install -r pyproject.toml` reads the dependency array directly
# without requiring the project to be a buildable package. Optional
# dependency groups (e.g. client / dev tooling) are intentionally
# skipped — main.py doesn't need them.
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy only the server — dev tools (client, decode_token, get_gitlab_token) are not needed at runtime
COPY main.py ./

# In a container the server must bind to all interfaces to be reachable from outside
ENV HOST=0.0.0.0

EXPOSE 8000

CMD ["python", "main.py"]
