@echo off
setlocal
cd /d "%~dp0"
set PORT=%~1
if "%PORT%"=="" set PORT=8010
python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload
