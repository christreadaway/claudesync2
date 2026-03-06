FROM python:3.11-slim

WORKDIR /app

# Install git (needed for repo scanning)
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent data directory
VOLUME /app/data

# Upload temp directory
RUN mkdir -p /tmp/claudesync_uploads

ENV HOST=0.0.0.0
ENV PORT=5111
ENV SCAN_PATHS=/repos

EXPOSE 5111

CMD ["gunicorn", "--bind", "0.0.0.0:5111", "--workers", "2", "--threads", "4", "--timeout", "120", "web_app:app"]
