#!/bin/sh

set -e

echo "Running default database migrations..."
python manage.py migrate --database=default

echo "Running deployment logs database migrations..."
python manage.py migrate --database=deployment_logs

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting application..."
exec "$@"