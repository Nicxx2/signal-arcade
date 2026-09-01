FROM node:24-alpine AS web
WORKDIR /build
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile
COPY frontend frontend
RUN pnpm --filter signal-arcade-web build

FROM python:3.12-slim AS runtime
ARG SIGNAL_ARCADE_VERSION=1.9.2
LABEL org.opencontainers.image.title="Signal Arcade" \
      org.opencontainers.image.description="A local-first Solana paper-trading and learning lab" \
      org.opencontainers.image.version="${SIGNAL_ARCADE_VERSION}" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.authors="Nicxx2"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SIGNAL_ARCADE_BIND=0.0.0.0 \
    SIGNAL_ARCADE_PORT=8765 \
    SIGNAL_ARCADE_DATA_DIR=/data \
    SIGNAL_ARCADE_FRONTEND_DIR=/app/frontend/dist
WORKDIR /app
RUN addgroup --system arcade && adduser --system --ingroup arcade arcade
COPY pyproject.toml LICENSE README.md THIRD_PARTY_NOTICES.md ./
COPY backend backend
COPY --from=web /build/frontend/dist frontend/dist
RUN python -m pip install --no-cache-dir --upgrade "pip==26.2.1" \
    && python -m pip install --no-cache-dir . \
    && mkdir /data \
    && chown arcade:arcade /data
USER arcade
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/v1/health', timeout=3))['ok']"
CMD ["signal-arcade"]
