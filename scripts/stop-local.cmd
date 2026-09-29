@echo off
schtasks /End /TN "TenderTrace-Feishu-Listener-E-tt" >nul 2>&1
schtasks /End /TN "TenderTrace-Local-E-tt"
exit /b %errorlevel%
