
# Stage 1: Build React frontend
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./

RUN npm install

COPY frontend/ ./

RUN npm run build


# Stage 2: Build Python backend
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

COPY . .

RUN pip install --no-cache-dir .


# Stage 3: Production
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser \
    && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents

USER appuser

WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build .

# Copy the built frontend into the production image
COPY --from=frontend-builder --chown=appuser:appuser /frontend/dist ./frontend/dist

# Start FastAPI
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
