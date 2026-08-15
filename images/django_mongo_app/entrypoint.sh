#!/bin/sh
set -e

echo "Starting gunicorn on 0.0.0.0:8000 (mongo variant, no Django migrations needed)..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
