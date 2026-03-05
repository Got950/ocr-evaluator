# OCR Evaluator - Run Script
# Run this after PostgreSQL is installed and .env is configured

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Check .env
if (-not (Test-Path .env)) {
    Write-Host "Creating .env from .env.example..."
    Copy-Item .env.example .env
    Write-Host "Please edit .env and set DATABASE_URL with your PostgreSQL password"
    Write-Host "Example: DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/ocr_evaluator"
    exit 1
}

Write-Host "Running database migrations..."
python -m alembic upgrade head

Write-Host "Starting OCR Evaluator server at http://127.0.0.1:8000"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
