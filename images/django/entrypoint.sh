#!/bin/sh
set -e

echo "Waiting for database at ${DB_HOST}:${DB_PORT}..."
ATTEMPTS=0
until python -c "
import socket, os, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect((os.environ['DB_HOST'], int(os.environ['DB_PORT'])))
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    ATTEMPTS=$((ATTEMPTS+1))
    if [ "$ATTEMPTS" -ge 30 ]; then
        echo "Database still not reachable after 30 attempts, starting anyway."
        break
    fi
    echo "Database not ready yet, retrying in 2s... (attempt $ATTEMPTS)"
    sleep 2
done

echo "Running migrations..."
python manage.py migrate --noinput || echo "Migration failed, continuing to start the server anyway."

echo "Starting gunicorn on 0.0.0.0:8000..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2
