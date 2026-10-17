param(
    [Parameter(Mandatory=$true)][string]$AgentRoot,
    [Parameter(Mandatory=$true)][string]$PythonExecutable,
    [string]$StateDirectory
)
$ErrorActionPreference = 'Stop'
try {
    if (-not $StateDirectory) { $StateDirectory=Join-Path $env:LOCALAPPDATA 'OpsAgent' }
    Add-Type -Path (Join-Path $AgentRoot 'deploy\AgentJobRunner.cs') -ErrorAction Stop
    $agentExitCode=[OpsAgentJob]::Run($PythonExecutable,$AgentRoot,$StateDirectory)
    exit $agentExitCode
} catch {
    # No exception, environment, command line or credential-bearing body is logged.
    Write-Error 'Read-only agent job failed; no credentials were logged.'
    exit 1
}
