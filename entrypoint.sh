#!/bin/sh

set -e

echo "Running  database migrations..."
python manage.py migrate 

python manage.py setup_wagtail_site

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting application..."
exec "$@"