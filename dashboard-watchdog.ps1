$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$statusPath = Join-Path $project "data\dashboard_watchdog_status.json"
$mutex = New-Object System.Threading.Mutex($true, "Local\AI-Video-Pipeline-OPS-Dashboard-Watchdog")

if (-not $mutex.WaitOne(0, $false)) {
    exit 0
}

function Write-WatchdogStatus {
    param([string]$State, [string]$Message)
    $directory = Split-Path -Parent $statusPath
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $temporary = "$statusPath.tmp"
    @{
        state = $State
        message = $Message
        updatedAt = [DateTimeOffset]::Now.ToString("o")
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $statusPath -Force
}

try {
    $config = Get-Content -LiteralPath (Join-Path $project "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $urlHost = [string]$config.listen_host
    if ($urlHost -eq "0.0.0.0") { $urlHost = "127.0.0.1" }
    $healthUrl = "http://${urlHost}:$($config.listen_port)/api/health"
    $launch = Join-Path $project "launch.ps1"

    while ($true) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-WatchdogStatus "running" "Dashboard health check passed"
                Start-Sleep -Seconds 5
                continue
            }
        } catch {}

        Write-WatchdogStatus "starting" "Dashboard is unavailable; starting it now"
        $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$launch`"")
        $process = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -WindowStyle Hidden -PassThru
        $healthy = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Seconds 2
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
                if ($response.StatusCode -eq 200) {
                    $healthy = $true
                    Write-WatchdogStatus "running" "Dashboard was restored by the watchdog"
                    break
                }
            } catch {}
            if ($process.HasExited) { break }
        }

        if (-not $healthy) {
            $exitCode = if ($process.HasExited) { $process.ExitCode } else { "still starting" }
            Write-WatchdogStatus "failed" "Dashboard start failed: $exitCode; retrying in 5 seconds"
        }
        if (-not $process.HasExited) { $process.WaitForExit() }
        Write-WatchdogStatus "restarting" "Dashboard exited with code $($process.ExitCode); restarting in 5 seconds"
        Start-Sleep -Seconds 5
    }
} catch {
    Write-WatchdogStatus "failed" ("Watchdog error: " + $_.Exception.Message)
    exit 1
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
