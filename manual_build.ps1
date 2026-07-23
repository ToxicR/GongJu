$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$FinalExeName = ([char]0x5DE5) + ([char]0x5177) + ([char]0x8F6F) + ([char]0x4EF6) + ".exe"
$DistDir = Join-Path $Root "dist"
$TempExe = Join-Path $DistDir "GongJu.exe"
$FinalExe = Join-Path $DistDir $FinalExeName

function Run-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "==> $Title"
    & $Action
}

Run-Step "Checking PyInstaller" {
    python -m pip show pyinstaller *> $null
    if ($LASTEXITCODE -ne 0) {
        python -m pip install pyinstaller
    }
}

Run-Step "Preparing bundled scrcpy" {
    python prepare_scrcpy.py
}

Run-Step "Building standalone exe" {
    if (Test-Path $TempExe) {
        Remove-Item -LiteralPath $TempExe -Force
    }
    if (Test-Path $FinalExe) {
        Remove-Item -LiteralPath $FinalExe -Force
    }

    python -m PyInstaller `
        --onefile `
        --windowed `
        --name GongJu `
        --clean `
        --add-data "bundled/platform-tools;bundled/platform-tools" `
        --add-data "bundled/scrcpy;bundled/scrcpy" `
        main.py

    if (!(Test-Path $TempExe)) {
        throw "PyInstaller did not create $TempExe"
    }

    Move-Item -LiteralPath $TempExe -Destination $FinalExe -Force
}

Write-Host ""
Write-Host "Build complete:"
Write-Host $FinalExe
