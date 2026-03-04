@echo off
set PWD=%~dp0
cd /d "%PWD%"
REM Add poppler (for PDF OCR) if installed via winget
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin" (
  set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin;%PATH%"
)
if not exist .env (
    echo Creating .env from template...
    echo DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/postgres> .env
)
echo Starting OCR Evaluator at http://127.0.0.1:8001
echo API docs: http://127.0.0.1:8001/docs
py -m uvicorn app.main:app --host 127.0.0.1 --port 8001
