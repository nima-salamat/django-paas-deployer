#!/bin/sh

set -e

echo "Running database migrations..."
python manage.py migrate

echo "Setting up Wagtail site..."
python manage.py setup_wagtail_site

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Migrating deployment log database..."
python manage.py migrate --database=deployment_logs

echo "Starting application..."
exec "$@"