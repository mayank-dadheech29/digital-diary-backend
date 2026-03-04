#!/bin/bash

# Configuration
DOMAIN="api.diarydoot.com"
EMAIL="your-email@example.com" # Should be passed as arg or read from .env

if [ -z "$1" ]; then
    echo "Usage: ./setup-ssl.sh <your-email>"
    exit 1
fi

EMAIL=$1

echo "Requesting SSL certificate for $DOMAIN..."

echo "Stopping Nginx temporarily to free up Port 80..."
docker compose stop nginx

# Run certbot in standalone mode (binds to Port 80 temporarily)
docker compose run --rm --entrypoint "certbot" -p 80:80 certbot certonly --standalone \
    --email $EMAIL --agree-tos --no-eff-email \
    -d $DOMAIN

echo "Starting Nginx again..."
docker compose up -d nginx

echo "Reloading Nginx to apply changes..."
docker compose exec nginx nginx -s reload
