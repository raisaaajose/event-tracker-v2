# Use Python 3.12 slim image as base
FROM python:3.12-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using pip
RUN pip install -e .

# Development stage
FROM base AS development

# Copy source code
COPY . .

# Generate Prisma client
RUN python -m prisma generate

# Expose port
EXPOSE 8000

# Command for development
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Production stage
FROM base AS production

# Copy source code
COPY . .

# Generate Prisma client as root so package writes are permitted
RUN python -m prisma generate

# Extract Prisma query engine to an app-owned location and make executable
RUN set -eux; \
    ENGINE_FILE="$(find /root/.cache/prisma-python -type f -name 'query-engine-*' | head -n1)"; \
    mkdir -p /app/.prisma; \
    cp "$ENGINE_FILE" /app/.prisma/query-engine; \
    chmod +x /app/.prisma/query-engine

# Create non-root user and prepare writable dirs
RUN adduser --disabled-password --gecos '' appuser && \
    mkdir -p /home/appuser/.cache && \
    chown -R appuser:appuser /home/appuser /app

# Switch to non-root user and set cache dir so prisma uses a writable location
USER appuser
ENV XDG_CACHE_HOME=/home/appuser/.cache \
    PRISMA_QUERY_ENGINE_BINARY=/app/.prisma/query-engine

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Command for production
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]