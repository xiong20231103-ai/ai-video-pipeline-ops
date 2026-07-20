$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $env:LOCALAPPDATA "TikHubOPS\venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "Installing Dashboard dependencies for first use..." -ForegroundColor Yellow
    & (Join-Path $project "install.ps1")
}

$config = Get-Content -LiteralPath (Join-Path $project "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$url = "http://127.0.0.1:$($config.listen_port)"

try {
    $existing = Invoke-WebRequest -UseBasicParsing -Uri "$url/api/health" -TimeoutSec 1
    if ($existing.StatusCode -eq 200) {
        Start-Process $url
        Write-Host "Dashboard is already running at $url" -ForegroundColor Green
        exit 0
    }
} catch {}

Start-Job -ScriptBlock {
    param($target)
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "$target/api/health" -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                Start-Process $target
                return
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
} -ArgumentList $url | Out-Null

Set-Location -LiteralPath $project
Write-Host "Dashboard is running at $url" -ForegroundColor Green
Write-Host "Closing this window stops only Dashboard, not the production tools." -ForegroundColor DarkGray
& $python app.py
