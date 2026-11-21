FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    CASCADASEN_DATA_DIR=/data
WORKDIR /app
# Dependencies first so code changes do not invalidate this layer
COPY pyproject.toml uv.lock ./
# Optional LLM (Claude API or Amazon Bedrock): docker compose build --build-arg WITH_LLM=1 backend
ARG WITH_LLM=0
RUN uv sync --locked --no-dev --no-install-project $( [ "$WITH_LLM" = "1" ] && echo --extra llm )
COPY src ./src
RUN uv sync --locked --no-dev $( [ "$WITH_LLM" = "1" ] && echo --extra llm )
EXPOSE 8000
CMD ["cascadasen-api"]
