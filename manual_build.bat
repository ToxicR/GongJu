@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==^> Checking PyInstaller
python -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
    python -m pip install pyinstaller
    if errorlevel 1 goto failed
)

echo.
echo ==^> Preparing bundled scrcpy
python prepare_scrcpy.py
if errorlevel 1 goto failed

echo.
echo ==^> Cleaning previous output
if exist "dist\GongJu.exe" del /f /q "dist\GongJu.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$name=([char]0x5DE5)+([char]0x5177)+([char]0x8F6F)+([char]0x4EF6)+'.exe'; $path=Join-Path 'dist' $name; Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue"
if errorlevel 1 goto failed

echo.
echo ==^> Building standalone exe
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name GongJu ^
    --clean ^
    --add-data "bundled/platform-tools;bundled/platform-tools" ^
    --add-data "bundled/scrcpy;bundled/scrcpy" ^
    main.py
if errorlevel 1 goto failed

if not exist "dist\GongJu.exe" (
    echo Build failed: dist\GongJu.exe was not created.
    goto failed
)

echo.
echo ==^> Renaming output
powershell -NoProfile -ExecutionPolicy Bypass -Command "$name=([char]0x5DE5)+([char]0x5177)+([char]0x8F6F)+([char]0x4EF6)+'.exe'; Move-Item -LiteralPath 'dist\GongJu.exe' -Destination (Join-Path 'dist' $name) -Force; Write-Host ('Build complete: ' + (Resolve-Path (Join-Path 'dist' $name)))"
if errorlevel 1 goto failed

if exist "GongJu.spec" del /f /q "GongJu.spec"

echo.
echo Done.
pause
exit /b 0

:failed
echo.
echo Build failed.
pause
exit /b 1
