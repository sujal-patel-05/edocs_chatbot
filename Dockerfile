FROM python:3.11-slim

WORKDIR /app

# Install system dependencies: p7zip for CHM extraction, curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    p7zip-full \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Grant write permissions for auto-extracting database in Hugging Face Spaces (user 1000)
RUN chmod -R 777 /app

EXPOSE 7860

CMD ["sh", "-c", "uvicorn src.edocs.api.app:app --host 0.0.0.0 --port ${PORT:-7860}"]
