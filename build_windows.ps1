$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Push-Location $ProjectDir
try {
    $env:PYTHONNOUSERSITE = "1"
    $env:PYTHONUSERBASE = Join-Path $ProjectDir ".py-userbase"
    New-Item -ItemType Directory -Force -Path $env:PYTHONUSERBASE | Out-Null
    $BuildUnpacked = Join-Path $ProjectDir ".build-unpacked"
    $BuildWheels = Join-Path $ProjectDir ".build-wheels"
    if (Test-Path $BuildUnpacked) {
        $env:PYTHONPATH = "$BuildUnpacked;$env:PYTHONPATH"
    }
    elseif (Test-Path $BuildWheels) {
        $WheelPaths = (Get-ChildItem -Path $BuildWheels -Filter "*.whl" | ForEach-Object { $_.FullName }) -join ";"
        if ($WheelPaths) {
            $env:PYTHONPATH = "$WheelPaths;$env:PYTHONPATH"
        }
    }
    & $Python -m PyInstaller --version | Out-Null
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --noconsole `
        --onefile `
        --name "LegalMarker" `
        --hidden-import "openpyxl" `
        --hidden-import "openpyxl.cell._writer" `
        --hidden-import "et_xmlfile" `
        --add-data "data;data" `
        --add-data "core;core" `
        --add-data ".wheels;.wheels" `
        "windows_marker.pyw"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
    Write-Host "Done: $ProjectDir\dist\LegalMarker.exe"
}
catch {
    Write-Host "PyInstaller is not installed for this Python."
    Write-Host "Install it first: $Python -m pip install pyinstaller"
    throw
}
finally {
    Pop-Location
}
