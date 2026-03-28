@echo off
REM SafeSave Backend - Production Startup Script (Windows)
REM This script handles all initialization and startup tasks

echo ======================================
echo SafeSave Backend - Startup Script
echo ======================================

REM Check if .env exists
if not exist ".env" (
    echo ERROR: .env file not found!
    echo Please copy .env.example to .env and configure it
    pause
    exit /b 1
)

echo Loading environment variables from .env...

REM Create logs directory
if not exist "logs" mkdir logs
echo + Logs directory ready

REM Check Python version
python --version
echo.

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat
echo + Virtual environment activated

REM Install/upgrade dependencies
echo Installing dependencies...
python -m pip install --upgrade pip setuptools wheel > nul 2>&1
pip install -r requirements.txt > nul 2>&1
echo + Dependencies installed

REM Verify database connectivity
echo Checking database connectivity...
python << 'EOF'
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

try:
    engine = create_engine(os.getenv("DATABASE_URL"))
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("+ Database connection successful")
except Exception as e:
    print(f"- Database connection failed: {e}")
    print("Please verify DATABASE_URL in .env file")
    exit(1)
EOF

echo.
echo ======================================
echo Starting SafeSave Backend API
echo ======================================

setlocal enabledelayedexpansion
for /f "tokens=2 delims==" %%a in ('findstr "ENVIRONMENT" .env') do set ENVIRONMENT=%%a
set "ENVIRONMENT=!ENVIRONMENT: =!"

if "!ENVIRONMENT!"=="production" (
    echo Starting with Gunicorn (Production Mode)...
    gunicorn main:app -w 4 -b 0.0.0.0:8000 -k uvicorn.workers.UvicornWorker --access-logfile logs/access.log --error-logfile logs/error.log
) else (
    echo Starting with Uvicorn (Development Mode)...
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
)

pause
