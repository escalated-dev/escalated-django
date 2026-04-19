#!/bin/sh
set -eu

cd /host

echo "[demo] waiting for postgres..."
until pg_isready -h db -p 5432 -U escalated >/dev/null 2>&1; do sleep 1; done

echo "[demo] migrate"
python manage.py migrate --noinput 2>&1 || echo "[demo] migrate skipped/failed"

echo "[demo] seed"
python manage.py seed_demo 2>&1 || echo "[demo] seed skipped (command missing)"

echo "[demo] ready"
exec "$@"
