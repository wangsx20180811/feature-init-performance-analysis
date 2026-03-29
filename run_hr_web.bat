@echo off
cd /d "%~dp0"
if not defined HR_WEB_PORT set HR_WEB_PORT=5001

echo.
echo [HR Web] Starting server on port %HR_WEB_PORT% ...
echo [HR Web] Keep the minimized window open, or the site will stop.
echo.

REM 优先使用 deploy.bat 创建的 venv，避免误用系统 Python 导致缺依赖
if exist "venv\Scripts\python.exe" (
  start "HR-Web-Server" /D "%~dp0" /min cmd /k "set HR_WEB_PORT=%HR_WEB_PORT% && venv\Scripts\python.exe main.py"
) else (
  start "HR-Web-Server" /D "%~dp0" /min cmd /k "set HR_WEB_PORT=%HR_WEB_PORT% && python main.py"
)

ping -n 4 127.0.0.1 >nul

start "" "http://127.0.0.1:%HR_WEB_PORT%/"

echo Opened browser: http://127.0.0.1:%HR_WEB_PORT%/
echo If the page fails, wait a few seconds and refresh (F5). Check the minimized window for errors.
echo.
exit /b 0
