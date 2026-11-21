FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    CASCADASEN_DATA_DIR=/data
WORKDIR /app
# Dependencies first so code changes do not invalidate this layer
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev
EXPOSE 8000
CMD ["cascadasen-api"]
