# syntax=docker/dockerfile:1

# Stage 1: build the front end. Everything it needs is bundled into web/dist,
# including dist/duckdb/** (the self-hosted DuckDB parquet extension).
FROM node:24-bookworm-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
# npm can skip esbuild's postinstall (install-script approval); run it explicitly.
RUN npm ci && node node_modules/esbuild/install.js
COPY web/ ./
RUN npm run build

# Stage 2: the read-only server.
FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIZ_HOST=0.0.0.0 \
    VIZ_PORT=8000 \
    VIZ_WEB_DIST=/app/web/dist
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY schemas/ schemas/
COPY skills/ skills/
COPY viz/ viz/
RUN pip install --no-cache-dir . && rm -rf /root/.cache
COPY --from=web /src/web/dist /app/web/dist
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin viz
USER 10001
EXPOSE 8000
CMD ["viz-server"]
