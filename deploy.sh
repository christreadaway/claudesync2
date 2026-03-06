#!/bin/bash
# Deploy ClaudeSync Dashboard to claudesync.treadaway.org
#
# Prerequisites:
#   1. Docker and docker-compose installed on the server
#   2. DNS: claudesync.treadaway.org pointing to the server IP
#   3. SSL certs in ./certs/ (fullchain.pem + privkey.pem)
#      - Use certbot: certbot certonly --standalone -d claudesync.treadaway.org
#      - Then: cp /etc/letsencrypt/live/claudesync.treadaway.org/*.pem ./certs/
#
# Usage:
#   # First time setup:
#   cp .env.example .env
#   # Edit .env with your password and paths
#   bash deploy.sh
#
#   # Update after code changes:
#   git pull
#   bash deploy.sh

set -e
cd "$(dirname "$0")"

# Check for .env file
if [ ! -f .env ]; then
    echo "ERROR: No .env file found."
    echo "Copy .env.example to .env and fill in your values:"
    echo "  cp .env.example .env"
    exit 1
fi

source .env

# Validate required vars
if [ -z "$DASHBOARD_PASSWORD" ]; then
    echo "ERROR: DASHBOARD_PASSWORD not set in .env"
    exit 1
fi

# Check for SSL certs
if [ ! -f certs/fullchain.pem ] || [ ! -f certs/privkey.pem ]; then
    echo "WARNING: SSL certs not found in ./certs/"
    echo "To get certs with certbot:"
    echo "  sudo certbot certonly --standalone -d claudesync.treadaway.org"
    echo "  mkdir -p certs"
    echo "  sudo cp /etc/letsencrypt/live/claudesync.treadaway.org/fullchain.pem certs/"
    echo "  sudo cp /etc/letsencrypt/live/claudesync.treadaway.org/privkey.pem certs/"
    echo ""
    echo "Running without SSL (HTTP only on port 5111)..."
    docker-compose up -d --build web
    echo ""
    echo "Dashboard running at http://$(hostname -I | awk '{print $1}'):5111"
    exit 0
fi

# Build and run with nginx
docker-compose up -d --build

echo ""
echo "Dashboard deployed to https://claudesync.treadaway.org"
echo "Login with your configured password."
