# Stage 1: Build Vue 3 + Vite + Tailwind frontend
FROM node:22-alpine AS web-builder
WORKDIR /build/web

COPY web/package.json web/package-lock.json* ./
RUN npm install

COPY web/ ./
RUN npm run build

# Stage 2: Python 3.12 FastAPI + Pillow + NumPy runtime serving API, WS & static web/dist on :8080
FROM python:3.12-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HRZN_PORT=8080 \
    HRZN_DATA_DIR=/app/data

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY server/ ./server/
COPY --from=web-builder /build/web/dist ./web/dist

RUN mkdir -p /app/data

EXPOSE 8080

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
