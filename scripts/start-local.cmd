@echo off
schtasks /Run /TN "TenderTrace-Local-E-tt"
if errorlevel 1 (
  echo The local background task is unavailable. Run scripts\serve-local.cmd instead.
  exit /b 1
)
schtasks /Run /TN "TenderTrace-Feishu-Listener-E-tt"
if errorlevel 1 (
  echo TenderTrace started, but the Feishu listener task is unavailable.
  echo Run scripts\feishu-listener.cmd in another terminal.
  exit /b 1
)
echo TenderTrace is starting at http://127.0.0.1:8000/
echo Feishu long-connection listener is starting.
