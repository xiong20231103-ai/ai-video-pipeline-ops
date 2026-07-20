$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $project
$runtimeRoot = Join-Path $env:LOCALAPPDATA "TikHubOPS"
$venvDir = Join-Path $runtimeRoot "venv"

Write-Host "Preparing AI Video Pipeline OPS Dashboard..." -ForegroundColor Cyan

$pythonCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    (Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike "*WindowsApps*") {
        $python = $pythonCommand.Source
    }
}
if (-not $python) {
    throw "Python was not found. Install Python 3.11 or newer first."
}

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
& $python -m venv $venvDir

$venvPython = Join-Path $venvDir "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host ""
Write-Host "Installation complete. Double-click Start Dashboard.cmd next time." -ForegroundColor Green
Read-Host "Press Enter to close"

