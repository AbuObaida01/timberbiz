#!/bin/bash

set -e

echo "🔄 Running database migrations..."
alembic upgrade head

echo "👥 Seeding admin accounts..."
python seed_admin.py

echo "🌲 Starting TimberBiz API..."
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1