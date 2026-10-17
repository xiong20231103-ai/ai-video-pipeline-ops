param(
    [Parameter(Mandatory=$true)][string]$AgentRoot,
    [Parameter(Mandatory=$true)][string]$PythonExecutable
)
$ErrorActionPreference = 'Stop'
try {
    $taskRuntime = Join-Path $env:LOCALAPPDATA 'OpsAgent'
    $taskPython = Start-Process -FilePath $PythonExecutable -ArgumentList @('-B','-m','agent.launcher') -WorkingDirectory $AgentRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRuntime 'task.stdout.log') -RedirectStandardError (Join-Path $taskRuntime 'task.stderr.log') -Wait -PassThru
    exit $taskPython.ExitCode
} catch {
    # Do not print exceptions, environment variables, configuration or command arguments.
    Write-Error 'Read-only agent could not start; credentials were not logged.'
    exit 1
}
