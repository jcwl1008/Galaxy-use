@echo off
cd /d "%~dp0"
if not exist "opencode.json" (
  echo Run SETUP.cmd first.
  pause
  exit /b 1
)
where opencode >nul 2>nul
if errorlevel 1 (
  echo Open OpenCode Desktop and choose this project folder:
  echo %CD%
  pause
  exit /b 1
)
call opencode
pause
