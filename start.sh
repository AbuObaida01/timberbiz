#!/bin/bash

echo "Running database migrations..."
alembic upgrade head

echo "Seeding admin accounts..."
python seed_admin.py

echo "Starting FastAPI server..."
uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}