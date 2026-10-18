param(
    [Parameter(Mandatory=$true)][string]$AgentRoot,
    [Parameter(Mandatory=$true)][string]$PythonExecutable,
    [string]$StateDirectory
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'agent-json.ps1')
try {
    if (-not $StateDirectory) { $StateDirectory=Join-Path $env:LOCALAPPDATA 'OpsAgent' }
    if ((Test-Path -LiteralPath (Join-Path $StateDirectory 'maintenance.json')) -or (Test-Path -LiteralPath (Join-Path $StateDirectory 'stop-request.json'))) {
        # No C# compilation, Python start or credential access while maintained.
        [void][IO.Directory]::CreateDirectory($StateDirectory)
        $target=Join-Path $StateDirectory 'task-job.json'
        $status=@{schema=2;wrapperPid=$PID;wrapperCreationFileTime=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToFileTimeUtc();launcherPid=0;phase='maintenance-blocked';exitCode=0;retryAfterSeconds=0;retryAt='';observedAt=[DateTime]::UtcNow.ToString('o')}
        Write-SharedAtomicJson -Path $target -Value $status
        exit 0
    }
    Add-Type -Path (Join-Path $AgentRoot 'deploy\AgentJobRunner.cs') -ErrorAction Stop
    $agentExitCode=[OpsAgentJob]::Supervise($PythonExecutable,$AgentRoot,$StateDirectory,60000)
    exit $agentExitCode
} catch {
    # No exception, environment, command line or credential-bearing body is logged.
    Write-Error 'Read-only agent job failed; no credentials were logged.'
    exit 1
}
