param(
    [ValidateSet('CrashRestart','LogonBefore','LogonAfter')][string]$Action='CrashRestart',
    [string]$RecordPath
)
$ErrorActionPreference='Stop'
$taskName='OpsConsoleReadonlyAgent';$agentRoot='E:\Backup\ops-agent'
$state=Join-Path $env:LOCALAPPDATA 'OpsAgent'
$python=Join-Path $env:LOCALAPPDATA 'TikHubOPS\venv_cuda\Scripts\python.exe'
$runtimePath=Join-Path $state 'agent-runtime.json'
function Read-AgentStatus { Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json }
function Write-AgentEvidence {
    $current=Read-AgentStatus
    $task=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
    $info=Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
    @{at=[DateTime]::UtcNow.ToString('o');taskState=[string]$task.State;lastTaskResult=$info.LastTaskResult;
      lastRunTime=$info.LastRunTime.ToUniversalTime().ToString('o');instanceId=$current.instanceId;
      pid=$current.pid;version=$current.version;phase=$current.phase;observedAt=$current.observedAt} | ConvertTo-Json -Compress
}
$task=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
if ($task.Description -ne 'OPS Console read-only agent; owned task; no production program control.' -or $task.Actions.Count -ne 1 -or $task.Actions[0].WorkingDirectory.TrimEnd('\') -ne $agentRoot) { throw 'Owned task mismatch.' }
$expected=(Get-Content -LiteralPath (Join-Path $agentRoot 'deployment-manifest.json') -Raw | ConvertFrom-Json).commit
$before=Read-AgentStatus
if ($task.State -ne 'Running' -or $before.phase -ne 'running' -or $before.version -ne $expected) { throw 'Expected agent must be running before acceptance.' }
if ($Action -eq 'LogonBefore') {
    if (-not $RecordPath -or (Test-Path -LiteralPath $RecordPath)) { throw 'Provide a new evidence file path.' }
    @{at=[DateTime]::UtcNow.ToString('o');instanceId=$before.instanceId;version=$expected;
      sessionId=(Get-Process -Id $PID).SessionId} | ConvertTo-Json | Set-Content -LiteralPath $RecordPath -Encoding utf8
    Write-AgentEvidence
    Write-Output 'Logon baseline saved. No logoff was performed. User must choose an idle pipeline window.'
    return
}
if ($Action -eq 'LogonAfter') {
    $baseline=Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json
    if ($before.instanceId -eq $baseline.instanceId -or $before.version -ne $baseline.version) { throw 'A different instance of the same version was not confirmed.' }
    $info=Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
    if ($info.LastRunTime.ToUniversalTime() -le [DateTime]::Parse($baseline.at).ToUniversalTime()) { throw 'No task launch after the logon baseline.' }
    Write-AgentEvidence
    Write-Output 'Different agent instance and new task run confirmed. Actual user logoff/logon confirmation is also required; this evidence alone is not proof of logoff.'
    return
}
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Crash test needs Administrator PowerShell for the existing hardened task process.' }
if ($task.Settings.RestartInterval -ne 'PT1M' -or $task.Settings.RestartCount -lt 1) { throw 'One-minute failure restart settings missing.' }
foreach ($name in @('stop-request.json','maintenance.json')) {
    if (Test-Path -LiteralPath (Join-Path $state $name)) { throw 'Maintenance active; crash test refused.' }
}
$job=Get-Content -LiteralPath (Join-Path $state 'task-job.json') -Raw | ConvertFrom-Json
if ($job.launcherPid -ne $before.parentPid) { throw 'Managed process tree identity mismatch.' }
$basePython=& $python -B -c 'import sys;print(sys._base_executable)'
if ($LASTEXITCODE -ne 0) { throw 'Interpreter unavailable.' }
$allowedExecutables=@($python.Trim(),$basePython.Trim())
$escapedPaths=($allowedExecutables | ForEach-Object { [Regex]::Escape($_) }) -join '|'
$launcherPattern='^(?:"(?:'+$escapedPaths+')"|(?:'+$escapedPaths+'))\s+-B\s+-m\s+agent\.launcher\s*$'
$process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$before.pid)
$owner=if ($process) { Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid } else { $null }
if (-not $process -or $process.CommandLine -notmatch $launcherPattern -or $process.ExecutablePath -notin $allowedExecutables -or $owner.ReturnValue -ne 0 -or $owner.Sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { throw 'Exact agent process identity not confirmed; no termination.' }
if ((Get-Process -Id $before.pid).StartTime.ToUniversalTime().ToFileTimeUtc() -ne [Int64]$before.processCreationFileTime) { throw 'Process identity changed.' }
Write-AgentEvidence
$started=[Diagnostics.Stopwatch]::StartNew()
# The helper rechecks the one lock holder and pins a handle + creation FILETIME.
& $python -B (Join-Path $PSScriptRoot 'agent_legacy_lock.py') $before.pid $before.processCreationFileTime
if ($LASTEXITCODE -ne 0) { throw 'Exact agent termination refused.' }
$recovered=$false
for ($attempt=0;$attempt -lt 360;$attempt++) {
    Write-AgentEvidence
    $after=Read-AgentStatus
    if ($after.instanceId -ne $before.instanceId -and $after.phase -eq 'running' -and $after.version -eq $expected -and (Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -eq 'Running') { $recovered=$true;break }
    Start-Sleep -Milliseconds 500
}
if (-not $recovered) { throw 'Automatic recovery not observed within 180 seconds. Agent was not manually started.' }
@{acceptance='actual-installed-task-crash-restart';configuredDelaySeconds=60;
  measuredRecoverySeconds=$started.Elapsed.TotalSeconds;oldInstance=$before.instanceId;
  newInstance=$after.instanceId;newPid=$after.pid;manuallyStarted=$false} | ConvertTo-Json -Compress
