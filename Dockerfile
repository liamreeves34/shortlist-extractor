#builder img that get's tossed after it's built
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/

WORKDIR /app

#tunrs all py files into bytecode as soon as the packages are installed then copies them to site-packages
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

# Install only what runs the service: no dev tools (pytest, ruff).
RUN uv sync --locked --no-dev

#-----------------------------------------------------------

#the img that gets shipped
FROM python:3.12-slim
WORKDIR /app

#only the finished env gets copied
COPY --from=builder /app/.venv /app/.venv

COPY service/ service/
COPY client/ client/

ENV PATH="/app/.venv/bin:$PATH" \
    EXTRACTOR_BACKEND=stub \
    CONNECTOR_MODE=stub

EXPOSE 8001

CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8001"]