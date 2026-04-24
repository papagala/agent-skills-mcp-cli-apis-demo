FROM python:3.12-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN uv sync --no-dev --no-editable


FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --home /home/app --create-home app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv

USER app
WORKDIR /home/app

EXPOSE 8000
CMD ["uvicorn", "tasks_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
