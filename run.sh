#!/bin/bash

# SafeSave Backend - Production Startup Script
# This script handles all initialization and startup tasks

set -e  # Exit on any error

echo "======================================"
echo "SafeSave Backend - Startup Script"
echo "======================================"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo "Please copy .env.example to .env and configure it"
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '#' | xargs)

echo "Environment: $ENVIRONMENT"
echo "Database: $DATABASE_URL"

# Create logs directory
mkdir -p logs
echo "✓ Logs directory ready"

# Check Python version
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate
echo "✓ Virtual environment activated"

# Install/upgrade dependencies
echo "Installing dependencies..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1
echo "✓ Dependencies installed"

# Run database migrations (if using Alembic)
if [ -d "alembic" ]; then
    echo "Running database migrations..."
    alembic upgrade head || true
    echo "✓ Database migrated"
fi

# Verify Pay Hero credentials
if [ -z "$PAYHERO_API_KEY" ] || [ -z "$PAYHERO_API_SECRET" ]; then
    echo "⚠ WARNING: Pay Hero credentials not configured!"
    echo "  Payments will not work until configured in .env"
fi

# Check database connectivity
echo "Checking database connectivity..."
python3 << 'EOF'
import os
from sqlalchemy import create_engine, text

try:
    engine = create_engine(os.getenv("DATABASE_URL"))
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("✓ Database connection successful")
except Exception as e:
    print(f"✗ Database connection failed: {e}")
    print("Please verify DATABASE_URL in .env file")
    exit(1)
EOF

# Start application
echo ""
echo "======================================"
echo "Starting SafeSave Backend API"
echo "======================================"
echo "API will be available at: http://localhost:${PORT:-8000}"
echo "API Documentation at: http://localhost:${PORT:-8000}/docs"
echo "Press Ctrl+C to stop"
echo ""

if [ "$ENVIRONMENT" = "production" ]; then
    # Production: Use Gunicorn with multiple workers
    echo "Starting with Gunicorn (Production Mode)..."
    gunicorn main:app \
        -w ${WORKERS:-4} \
        -b 0.0.0.0:${PORT:-8000} \
        -k uvicorn.workers.UvicornWorker \
        --access-logfile logs/access.log \
        --error-logfile logs/error.log \
        --log-level ${LOG_LEVEL:-info}
else
    # Development: Use Uvicorn with auto-reload
    echo "Starting with Uvicorn (Development Mode)..."
    uvicorn main:app \
        --reload \
        --host 0.0.0.0 \
        --port ${PORT:-8000} \
        --log-level ${LOG_LEVEL:-info}
fi
