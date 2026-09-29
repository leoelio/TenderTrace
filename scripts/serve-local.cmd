@echo off
setlocal
cd /d "%~dp0.."
if /I "%~1"=="--log" goto log
if not exist ".venv\Scripts\python.exe" (
  echo Install the project virtual environment first; see README.md.
  exit /b 1
)
rem Local business mode: keep the Web app and scheduled Feishu delivery running.
set "TENDERTRACE_HOST=127.0.0.1"
set "TENDERTRACE_SCHEDULER_ENABLED=true"
set "TENDERTRACE_DELIVERY_CHANNELS=web,outbox,feishu_bitable"
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" -m tendertrace serve
exit /b %errorlevel%

:log
if not exist "logs" mkdir "logs"
call "%~f0" >> "logs\local-service.log" 2>&1
exit /b %errorlevel%
