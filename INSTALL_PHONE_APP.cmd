@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Run SETUP.cmd first.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" install_phone_app.py
pause
