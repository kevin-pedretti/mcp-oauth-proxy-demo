FROM registry.access.redhat.com/ubi9/python-312

WORKDIR /app

# Install dependencies before copying source so this layer is cached
COPY pyproject.toml .
RUN pip install --no-cache-dir fastmcp "PyJWT[crypto]"

# Copy only the server — dev tools (client, decode_token, get_gitlab_token) are not needed at runtime
COPY main.py .

# In a container the server must bind to all interfaces to be reachable from outside
ENV HOST=0.0.0.0

EXPOSE 8000

CMD ["python", "main.py"]
