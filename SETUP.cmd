@echo off
cd /d "%~dp0"
py -3 setup_bridge.py
if errorlevel 1 echo Setup did not complete. Copy the error above.
pause
