FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WORKSPACE_ROOT=/workspace \
    MCP_PORT=8051

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

EXPOSE 8051

ENTRYPOINT ["bsl-mcp"]
