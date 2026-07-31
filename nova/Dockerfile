FROM python:3.12-slim

# uv : gestionnaire de paquets Python moderne, tres rapide.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

# On copie d'abord les dependances : Docker met cette couche en cache et ne la
# reconstruit que si pyproject.toml change. Les rebuilds deviennent quasi instantanes.
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

COPY migrations ./migrations
COPY config ./config

EXPOSE 8100
CMD ["sh", "-c", "nova db migrate && uvicorn nova.api.app:app --host 0.0.0.0 --port 8100"]
