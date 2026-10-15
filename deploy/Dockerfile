# Multi-stage, non-root, offline-capable container definition
FROM python:3.11-slim AS runtime

# Security hardening: Prevent bytecode caching to read-only layers and unbuffer output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

# Install essential runtime libraries if needed (PyMuPDF dependencies)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

WORKDIR /app

# In an air-gapped environment, wheels are staged in ./deploy/wheelhouse/
# If present, pip installs strictly from the internal wheelhouse offline.
COPY pyproject.toml ./
COPY deploy/wheelhouse* ./wheelhouse/

# Install dependencies using pinned pyproject.toml
RUN if [ -d "./wheelhouse" ] && [ "$(ls -A ./wheelhouse)" ]; then \
        pip install --no-cache-dir --no-index --find-links=./wheelhouse -e .; \
    else \
        pip install --no-cache-dir -e .; \
    fi

# Copy application source code and documentation
COPY app ./app
COPY docs ./docs

# Ensure strict file ownership
RUN chown -R appuser:appgroup /app

USER appuser:appgroup

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health/live || exit 1

ENTRYPOINT ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
