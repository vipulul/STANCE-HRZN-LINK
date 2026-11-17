# Stage 1: Build Vue 3 + Vite + Tailwind frontend
FROM node:22-alpine AS web-builder
WORKDIR /build/web

COPY web/package.json web/package-lock.json* ./
RUN npm install

COPY plugins/ ../plugins/
COPY web/ ./
RUN npm run build

# Stage 2: Python 3.12 FastAPI + Playwright + NumPy runtime serving API, WS & static web/dist on :8080
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HRZN_PORT=8080 \
    HRZN_DATA_DIR=/app/data

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt \
    && playwright install --with-deps chromium

COPY server/ ./server/
COPY plugins/ ./plugins/
COPY --from=web-builder /build/web/dist ./web/dist

RUN mkdir -p /app/data

EXPOSE 8080

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
