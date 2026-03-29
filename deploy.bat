@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo === CASE-Excel_merge 一键部署（Windows）===
echo 项目目录: %~dp0
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.10+ 并加入 PATH。
  pause
  exit /b 1
)

if not exist "venv\" (
  echo [1/2] 创建虚拟环境 venv ...
  python -m venv venv
  if errorlevel 1 (
    echo [错误] 创建 venv 失败。
    pause
    exit /b 1
  )
) else (
  echo [1/2] 已存在 venv，跳过创建。
)

echo [2/2] 安装/更新依赖 requirements.txt ...
call "%~dp0venv\Scripts\activate.bat"
python -m pip install -U pip
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo [错误] pip install 失败。
  pause
  exit /b 1
)

echo.
echo 部署完成。
echo 下一步: 双击 run_hr_web.bat 或在已激活 venv 下执行  python main.py
echo.
pause
exit /b 0
