FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir build && pip wheel --no-cache-dir -w /wheels -e .

FROM python:3.11-slim
WORKDIR /app
# Install git for persona sync feature
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY prism/ ./prism/
COPY personas/ ./personas/
ENV PRISM_DB_PATH=/data/prism.db
CMD ["python", "-m", "prism"]

