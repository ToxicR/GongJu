@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist build mkdir build
cd build

where cmake >nul 2>&1
if %errorlevel% neq 0 (
    echo 未找到 cmake，请安装 CMake 或将 cmake 加入 PATH。
    echo 或使用 Visual Studio 打开本目录并生成解决方案。
    pause
    exit /b 1
)

REM 优先 VS 2022，其次 2019
if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe" (
    cmake .. -G "Visual Studio 17 2022" -A x64
) else if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\Common7\IDE\devenv.exe" (
    cmake .. -G "Visual Studio 16 2019" -A x64
) else (
    cmake .. -G "Visual Studio 17 2022" -A x64
)

if %errorlevel% neq 0 (
    echo CMake 配置失败。
    pause
    exit /b 1
)

cmake --build . --config Release
if %errorlevel% neq 0 (
    echo 编译失败。
    pause
    exit /b 1
)

echo.
echo 编译完成。可执行文件：build\Release\GongjuCpp.exe
pause
