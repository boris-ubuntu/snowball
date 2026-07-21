FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2 and potential other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY backend/ /app/

# Copy securities dump for seeding
COPY securities_dump.json /app/securities_dump.json

# Copy frontend (for serving static files)
COPY frontend/ /frontend/

EXPOSE 8000

# Use uvicorn for production — single worker fits Render free tier (512 MB RAM)
# Override with WEB_CONCURRENCY env var if needed
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
