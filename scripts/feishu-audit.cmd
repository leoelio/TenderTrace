@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Missing .venv\Scripts\python.exe
  exit /b 1
)

echo [1/5] Redacted configuration
".venv\Scripts\python.exe" -m tendertrace config-check
if errorlevel 1 exit /b %errorlevel%

echo.
echo [2/5] Feishu messaging app
".venv\Scripts\python.exe" -m tendertrace feishu-status
if errorlevel 1 exit /b %errorlevel%

echo.
echo [3/5] Feishu agent app
".venv\Scripts\python.exe" -m tendertrace feishu-agent-status
if errorlevel 1 exit /b %errorlevel%

echo.
echo [4/5] Feishu Bitable read-only check
".venv\Scripts\python.exe" -m tendertrace feishu-bitable-check
if errorlevel 1 exit /b %errorlevel%

echo.
echo [5/5] Local subscriptions
".venv\Scripts\python.exe" -m tendertrace list-subscriptions
if errorlevel 1 exit /b %errorlevel%

echo.
echo [OK] Read-only audit completed. No message sent and no Feishu data changed.
