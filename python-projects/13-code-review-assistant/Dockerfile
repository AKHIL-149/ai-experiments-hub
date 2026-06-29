# Multi-stage Dockerfile for AI Code Review Assistant
# Production-ready with minimal image size and security hardening

# Stage 1: Builder - Install dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies in virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - Minimal production image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_HOME=/app \
    LOG_LEVEL=INFO

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create app user and directories for security
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /app/data/repos /app/data/logs && \
    chown -R appuser:appuser /app

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code with proper ownership
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser static/ ./static/
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser server.py .
COPY --chown=appuser:appuser celery_app.py .
COPY --chown=appuser:appuser .env.example .env.example
COPY --chown=appuser:appuser healthcheck.sh .

# Make healthcheck script executable
RUN chmod +x healthcheck.sh

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

# Health check using dedicated script
# - interval: How often to run the check (30s)
# - timeout: How long to wait for check to complete (10s)
# - start-period: Grace period during startup (40s)
# - retries: Consecutive failures before marking unhealthy (3)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["/app/healthcheck.sh"]

# Default command (override in docker-compose for different services)
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
