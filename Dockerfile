FROM python:3.11-slim AS builder
WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.11-slim
WORKDIR /app

# Install git for persona sync feature
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Copy uv and virtual environment from builder
COPY --from=builder /bin/uv /bin/uv
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY prism/ ./prism/
COPY personas/ ./personas/
COPY pyproject.toml ./

# Install the project itself
RUN /bin/uv sync --frozen --no-dev

ENV PRISM_DB_PATH=/data/prism.db
ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "prism"]
