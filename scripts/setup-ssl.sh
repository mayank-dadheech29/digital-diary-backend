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

# Create the directories if they don't exist
mkdir -p certbot/conf
mkdir -p certbot/www

# Run certbot to get the certificate
docker compose run --rm certbot certonly --webroot --webroot-path=/var/www/certbot \
    --email $EMAIL --agree-tos --no-eff-email \
    -d $DOMAIN

echo "Reloading Nginx to apply changes..."
docker compose exec nginx nginx -s reload
