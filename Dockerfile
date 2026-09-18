# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.14-slim

# ── Build-Stage: Abhängigkeiten und Paket mit uv in ein venv installieren ──
FROM ${PYTHON_IMAGE} AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.16 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Erst nur die Abhängigkeiten (gut cachebar), dann das Projekt selbst
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ── Runtime-Stage: schlankes Image ohne Build-Werkzeuge ──
FROM ${PYTHON_IMAGE}

LABEL org.opencontainers.image.title="matrix-bot-tools" \
      org.opencontainers.image.description="Matrix-Tools für Hochschulgruppen: Watchdog, Broadcast, Raum-Erstellung und Mitglieder-Sync." \
      org.opencontainers.image.source="https://github.com/Fachschaft-Media/matrix-bot-tools"

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir /data \
    && chown app:app /data

COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    MATRIX_TOOLS_DATA_DIR=/data \
    MATRIX_TOOLS_IN_DOCKER=1

WORKDIR /data
VOLUME ["/data"]
USER app

# Port für den SSO-Callback von 'matrix-tools login'
EXPOSE 8765

ENTRYPOINT ["matrix-tools"]
CMD ["watchdog"]
