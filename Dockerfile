# ==============================================================================
# AI Clipper - Multi-Stage Production Dockerfile
# Stage 1: Build React Production Bundle
# Stage 2: Python 3.11 Slim Runtime with FFmpeg, Fonts, and FastAPI Server
# ==============================================================================

# --- Stage 1: Frontend Builder ---
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Copy dependency manifests first to leverage Docker layer caching
COPY frontend/package.json ./
RUN npm install

# Copy source and build static artifacts
COPY frontend/ ./
RUN npm run build


# --- Stage 2: Production Python Runtime ---
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies: FFmpeg, libass, DejaVu/FreeFont TTF fonts, OpenCV libs, curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libass9 \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    libgl1 \
    libglib2.0-0 \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend application source and assets
COPY backend/ ./backend/
COPY assets/ ./assets/

# Copy compiled React frontend bundle from Stage 1 into frontend/dist
COPY --from=frontend-builder /build/dist ./frontend/dist

# Ensure persistent directories exist and are writable
RUN mkdir -p /app/output /app/temp /app/config/credentials

# Expose backend API / SPA port
EXPOSE 8000

# Container Healthcheck targeting the API health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Start Uvicorn ASGI server
CMD ["uvicorn", "backend.app.server:app", "--host", "0.0.0.0", "--port", "8000"]
