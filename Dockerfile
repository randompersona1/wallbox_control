FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /wallbox


COPY . .

RUN uv sync --locked --no-dev

ENV PATH="/wallbox/.venv/bin:$PATH"

ENTRYPOINT []

EXPOSE 8000
CMD ["wallbox"]