$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $project 'deploy\pip\SessionGuard.ps1')
$startupPermission = Get-PipStartupPermission
if (-not $startupPermission.Allow) {
    Write-PipStartupSkip -LogDirectory (Join-Path $project 'data\session-guard') -Role 'dashboard-launch' -Decision $startupPermission
    exit 0
}
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
# The project directory contains spaces.  Passing a bare relative script name
# lets a broken/inherited working directory split it at "New project" and the
# watchdog then loops without ever bringing 8765 online.
$shadowSettings = 'E:\Backup\ops-shadow-control-v3\host-settings.json'
if (Test-Path -LiteralPath $shadowSettings -PathType Leaf) {
    $shadowHelperReady=$false
    try {
        . (Join-Path $project 'deploy\shadow-launch.ps1')
        $shadowHelperReady=$true
    } catch {}
    if ($shadowHelperReady) {
        Invoke-ShadowOrLegacy -Python $python -Project $project -SettingsPath $shadowSettings
        exit $LASTEXITCODE
    }
    # A missing/broken optional helper uses the unchanged entry exactly once.
    & $python (Join-Path $project "app.py")
    exit $LASTEXITCODE
}
& $python (Join-Path $project "app.py")
