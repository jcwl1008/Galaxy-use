@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP.cmd first.
) else (
  ".venv\Scripts\python.exe" phone_mcp.py --doctor
)
pause
