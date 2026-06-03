#!/bin/sh
set -e

echo "Starting entrypoint script"

# Wait for DB if a host is provided (best-effort)
if [ -n "$MONGODB_HOST" ]; then
  echo "MongoDB host: $MONGODB_HOST"
fi

echo "Applying database migrations (if any)"
python manage.py migrate --noinput || true

echo "Collecting static files"
python manage.py collectstatic --noinput || true

exec "$@"

#!/bin/sh
set -e

echo "Starting entrypoint script"

# Wait for DB if a host is provided (best-effort)
if [ -n "$MONGODB_HOST" ]; then
  echo "MongoDB host: $MONGODB_HOST"
fi

echo "Applying database migrations (if any)"
python manage.py migrate --noinput || true

echo "Collecting static files"
python manage.py collectstatic --noinput || true

exec "$@"
