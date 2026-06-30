@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 优先使用 py 启动器，其次 python
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -m pip install -r requirements.txt -q
    py main.py
    goto :end
)
where python >nul 2>&1
if %errorlevel% equ 0 (
    python -m pip install -r requirements.txt -q
    python main.py
    goto :end
)

echo 未检测到 Python，请先安装 Python 3.8 或更高版本。
echo 下载地址: https://www.python.org/downloads/
echo 安装时请勾选 "Add Python to PATH"。
:end
pause
