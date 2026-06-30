@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在安装打包工具 PyInstaller...
python -m pip install pyinstaller -q

echo.
echo 正在打包为独立 exe（不依赖 Python）...
pyinstaller --onefile --windowed --name "工具软件" --clean --add-data "bundled/platform-tools;bundled/platform-tools" main.py

if %errorlevel% neq 0 (
    echo 打包失败。
    pause
    exit /b 1
)

echo.
echo 打包完成。可执行文件位置: dist\工具软件.exe
echo 将 dist\工具软件.exe 发送给他人即可使用，对方无需安装 Python。
echo.
pause
