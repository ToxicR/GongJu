@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 优先使用 PATH 中的 dotnet，再尝试常见安装路径
where dotnet >nul 2>&1
if %errorlevel% equ 0 (
    dotnet run --project GongjuCSharp
    goto :end
)

if exist "%ProgramFiles%\dotnet\dotnet.exe" (
    "%ProgramFiles%\dotnet\dotnet.exe" run --project GongjuCSharp
    goto :end
)

if exist "%ProgramFiles(x86)%\dotnet\dotnet.exe" (
    "%ProgramFiles(x86)%\dotnet\dotnet.exe" run --project GongjuCSharp
    goto :end
)

if exist "%LOCALAPPDATA%\Microsoft\dotnet\dotnet.exe" (
    "%LOCALAPPDATA%\Microsoft\dotnet\dotnet.exe" run --project GongjuCSharp
    goto :end
)

echo 未检测到 .NET 运行时，无法直接运行 C# 程序。
echo.
echo 请先安装 .NET 8 SDK 后重试：
echo   winget install Microsoft.DotNet.SDK.8
echo 或从 https://dotnet.microsoft.com/download/dotnet/8.0 下载安装。
echo.
:end
pause
