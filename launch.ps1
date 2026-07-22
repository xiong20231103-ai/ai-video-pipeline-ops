$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $env:LOCALAPPDATA "TikHubOPS\venv_cuda\Scripts\python.exe"

if (Test-Path -LiteralPath $python) {
    # A venv can remain on disk after its base Python was removed.  Verify it
    # before using it so the dashboard can repair itself instead of silently
    # disappearing at the next restart.
    & $python -c "import fastapi, uvicorn, psutil" *> $null
    if ($LASTEXITCODE -ne 0) { $python = "" }
}

if (-not $python) {
    & (Join-Path $project "install.ps1")
    $python = Join-Path $env:LOCALAPPDATA "TikHubOPS\venv_cuda\Scripts\python.exe"
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Installing Dashboard dependencies for first use..." -ForegroundColor Yellow
    & (Join-Path $project "install.ps1")
    $python = Join-Path $env:LOCALAPPDATA "TikHubOPS\venv_cuda\Scripts\python.exe"
}

$config = Get-Content -LiteralPath (Join-Path $project "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$urlHost = [string]$config.listen_host
if ($urlHost -eq "0.0.0.0") {
    $urlHost = "127.0.0.1"
}
$url = "http://${urlHost}:$($config.listen_port)"

try {
    $existing = Invoke-WebRequest -UseBasicParsing -Uri "$url/api/health" -TimeoutSec 1
    if ($existing.StatusCode -eq 200) {
        Write-Host "Dashboard is already running at $url" -ForegroundColor Green
        exit 0
    }
} catch {}

Set-Location -LiteralPath $project
Write-Host "Dashboard is running at $url" -ForegroundColor Green
& $python app.py
