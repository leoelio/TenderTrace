@echo off
setlocal
cd /d "%~dp0.."
if /I "%~1"=="--log" goto log
if not exist ".venv\Scripts\python.exe" (
  echo Install the project virtual environment first; see README.md.
  exit /b 1
)
rem The Web service owns subscription scheduling. This process only receives Feishu events.
set "TENDERTRACE_SCHEDULER_ENABLED=false"
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" -m tendertrace feishu-bot-listen
exit /b %errorlevel%

:log
if not exist "logs" mkdir "logs"
call "%~f0" >> "logs\feishu-listener.log" 2>&1
exit /b %errorlevel%
