# ---------------------------------------------------------------------------
# KALBI-2 Autonomous Trading System
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# System dependencies required by pandas-ta, psycopg2-binary, numpy, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        make \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Copy application source
COPY src/ ./src/

# Ensure the src package is importable
ENV PYTHONPATH="/app"

# Default command: run the main scheduler entry point
CMD ["python", "-m", "src.main"]
