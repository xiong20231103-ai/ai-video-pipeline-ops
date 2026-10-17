param(
    [ValidateSet('CrashRestart','SupervisorRestart','Maintenance','RecoveryAll','LogonBefore','LogonAfter')][string]$Action='RecoveryAll',
    [string]$RecordPath
)
$ErrorActionPreference='Stop'
$taskName='OpsConsoleReadonlyAgent';$agentRoot='E:\Backup\ops-agent'
$state=Join-Path $env:LOCALAPPDATA 'OpsAgent'
$python=Join-Path $env:LOCALAPPDATA 'TikHubOPS\venv_cuda\Scripts\python.exe'
$runtimePath=Join-Path $state 'agent-runtime.json';$jobPath=Join-Path $state 'task-job.json'
$helper=Join-Path $PSScriptRoot 'agent_source_update.py';$control=Join-Path $PSScriptRoot 'agent_legacy_lock.py'
$expected=(Get-Content -LiteralPath (Join-Path $agentRoot 'deployment-manifest.json') -Raw | ConvertFrom-Json).commit
function Read-Agent { Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json }
function Read-Job { Get-Content -LiteralPath $jobPath -Raw | ConvertFrom-Json }
function Test-AgentAlive($Runtime) {
    try { return ((Get-Process -Id $Runtime.pid -ErrorAction Stop).StartTime.ToUniversalTime().ToFileTimeUtc() -eq [Int64]$Runtime.processCreationFileTime) } catch { return $false }
}
function Write-Evidence([string]$Stage) {
    $runtime=Read-Agent;$job=Read-Job
    $task=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
    $info=Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
    @{at=[DateTime]::UtcNow.ToString('o');stage=$Stage;taskState=[string]$task.State;lastTaskResult=$info.LastTaskResult;
      lastRunFileTime=$info.LastRunTime.ToUniversalTime().ToFileTimeUtc();nextRunAt=$info.NextRunTime.ToUniversalTime().ToString('o');
      instanceId=$runtime.instanceId;pid=$runtime.pid;version=$runtime.version;runtimePhase=$runtime.phase;agentAlive=(Test-AgentAlive $runtime);
      supervisorPid=$job.wrapperPid;jobPhase=$job.phase;jobExitCode=$job.exitCode;retryAfterSeconds=$job.retryAfterSeconds} | ConvertTo-Json -Compress
}
function Assert-OwnedTask {
    $task=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
    $arguments='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$agentRoot+'\deploy\agent-run.ps1" -AgentRoot "'+$agentRoot+'" -PythonExecutable "'+$python+'"'
    $executable=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if ($task.Description -ne 'OPS Console read-only agent; owned task; no production program control.' -or $task.Actions.Count -ne 1 -or $task.Actions[0].WorkingDirectory.TrimEnd('\') -ne $agentRoot -or $task.Actions[0].Execute -ne $executable -or $task.Actions[0].Arguments -ne $arguments) { throw 'Owned task identity mismatch.' }
    $repeat=@($task.Triggers | Where-Object { $_.Repetition.Interval -eq 'PT5M' -and [string]::IsNullOrEmpty($_.Repetition.Duration) })
    if ($task.Triggers.Count -ne 2 -or $repeat.Count -ne 1 -or $task.Settings.MultipleInstances -ne 2) { throw 'Expected same-task indefinite five-minute fallback and IgnoreNew.' }
    return $task
}
function Assert-Running {
    $runtime=Read-Agent;$job=Read-Job;$task=Assert-OwnedTask
    if ($task.State -ne 'Running' -or $runtime.phase -ne 'running' -or $runtime.version -ne $expected -or $job.phase -ne 'running' -or $job.launcherPid -ne $runtime.parentPid -or -not (Test-AgentAlive $runtime)) { throw 'Expected live agent and supervisor not confirmed.' }
    return $runtime
}
function Assert-ExactProcess([Int64]$ProcessNumber,[Int64]$Created,[string]$Kind) {
    $process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$ProcessNumber)
    if (-not $process) { throw 'Expected process disappeared; no termination.' }
    $owner=Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid
    if ($owner.ReturnValue -ne 0 -or $owner.Sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -or (Get-Process -Id $ProcessNumber).StartTime.ToUniversalTime().ToFileTimeUtc() -ne $Created) { throw 'Process owner/creation changed; no termination.' }
    if ($Kind -eq 'agent') {
        $basePython=& $python -B -c 'import sys;print(sys._base_executable)'
        if ($LASTEXITCODE) { throw 'Interpreter query failed.' }
        $allowed=@($python,$basePython.Trim())
        $paths=($allowed | ForEach-Object { [Regex]::Escape($_) }) -join '|'
        $pattern='^(?:"(?:'+$paths+')"|(?:'+$paths+'))\s+-B\s+-m\s+agent\.launcher\s*$'
        if ($process.ExecutablePath -notin $allowed -or $process.CommandLine -notmatch $pattern) { throw 'Exact Python launcher mismatch; no termination.' }
    } else {
        $task=Assert-OwnedTask
        $exe=[Regex]::Escape($task.Actions[0].Execute)
        $pattern='^(?:"'+$exe+'"|'+$exe+')\s+'+[Regex]::Escape($task.Actions[0].Arguments)+'\s*$'
        if ($process.ExecutablePath -ne $task.Actions[0].Execute -or $process.CommandLine -notmatch $pattern) { throw 'Exact supervisor task action mismatch; no termination.' }
    }
}
function Wait-Recovery($Old,[Int64]$OldSupervisor,[string]$Stage,[Diagnostics.Stopwatch]$Watch,[double]$Limit) {
    $script:Recovered=$null
    while ($Watch.Elapsed.TotalSeconds -lt $Limit) {
        Write-Evidence $Stage
        $runtime=Read-Agent;$job=Read-Job
        $supervisorMatches=($Stage -eq 'python-crash' -and $job.wrapperPid -eq $OldSupervisor) -or ($Stage -ne 'python-crash' -and $job.wrapperPid -ne $OldSupervisor)
        if ($runtime.instanceId -ne $Old.instanceId -and $runtime.phase -eq 'running' -and $runtime.version -eq $expected -and $job.phase -eq 'running' -and $supervisorMatches -and (Test-AgentAlive $runtime) -and (Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -eq 'Running') { $script:Recovered=$runtime;return }
        Start-Sleep -Milliseconds 500
    }
    @{acceptance=$Stage;result='failed';observedSeconds=$Watch.Elapsed.TotalSeconds;manualStart=$false} | ConvertTo-Json -Compress
    throw ('Automatic recovery not observed; actual elapsed seconds: '+$Watch.Elapsed.TotalSeconds)
}
$null=Assert-OwnedTask
$before=Assert-Running
if ($Action -eq 'LogonBefore') {
    if (-not $RecordPath -or (Test-Path -LiteralPath $RecordPath)) { throw 'Provide a new evidence record path.' }
    @{at=[DateTime]::UtcNow.ToString('o');capturedFileTime=[DateTime]::UtcNow.ToFileTimeUtc();instanceId=$before.instanceId;version=$expected;sessionId=(Get-Process -Id $PID).SessionId} | ConvertTo-Json | Set-Content -LiteralPath $RecordPath -Encoding utf8
    Write-Evidence 'logon-before';Write-Output 'Baseline saved; user chooses idle window. No logoff was performed.';return
}
if ($Action -eq 'LogonAfter') {
    $baseline=Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json
    $info=Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
    if ($before.instanceId -eq $baseline.instanceId -or $before.version -ne $baseline.version -or $info.LastRunTime.ToUniversalTime().ToFileTimeUtc() -le [Int64]$baseline.capturedFileTime) { throw 'New same-version task instance after baseline not confirmed.' }
    Write-Evidence 'logon-after';Write-Output 'New task instance confirmed; actual user logoff/logon confirmation is also required.';return
}
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Exact installed process crash tests require Administrator PowerShell.' }
foreach ($name in @('maintenance.json','stop-request.json')) { if (Test-Path -LiteralPath (Join-Path $state $name)) { throw 'Maintenance active; recovery tests refused.' } }
if ($Action -in @('RecoveryAll','CrashRestart')) {
    $before=Assert-Running;$job=Read-Job
    Assert-ExactProcess $before.pid $before.processCreationFileTime 'agent'
    Write-Evidence 'python-crash-before';$watch=[Diagnostics.Stopwatch]::StartNew()
    & $python -B $control $before.pid $before.processCreationFileTime
    if ($LASTEXITCODE) { throw 'Pinned agent termination refused.' }
    Wait-Recovery $before $job.wrapperPid 'python-crash' $watch 180
    @{acceptance='actual-python-crash-recovery';result='passed';configuredDelaySeconds=60;actualRecoverySeconds=$watch.Elapsed.TotalSeconds;oldPid=$before.pid;newPid=$script:Recovered.pid;oldInstance=$before.instanceId;newInstance=$script:Recovered.instanceId;manualStart=$false} | ConvertTo-Json -Compress
}
if ($Action -in @('RecoveryAll','SupervisorRestart')) {
    $before=Assert-Running;$job=Read-Job
    Assert-ExactProcess $job.wrapperPid $job.wrapperCreationFileTime 'supervisor'
    Write-Evidence 'supervisor-crash-before';$watch=[Diagnostics.Stopwatch]::StartNew()
    & $python -B $control --supervisor $job.wrapperPid $job.wrapperCreationFileTime
    if ($LASTEXITCODE) { throw 'Pinned supervisor termination refused.' }
    $released=$false;$releaseWatch=[Diagnostics.Stopwatch]::StartNew()
    while ($releaseWatch.Elapsed.TotalSeconds -lt 10) {
        & $python -B $helper probe
        if ($LASTEXITCODE -eq 0 -and -not (Test-AgentAlive $before)) { $released=$true;break }
        Start-Sleep -Milliseconds 100
    }
    if (-not $released) { throw 'Supervisor ended but old agent/lock remained; no recovery pass.' }
    @{stage='supervisor-crash-tree-exit';oldAgentAlive=$false;lockFree=$true;observedSeconds=$releaseWatch.Elapsed.TotalSeconds} | ConvertTo-Json -Compress
    # No manual start. The same task's real five-minute trigger must recover it.
    Wait-Recovery $before $job.wrapperPid 'supervisor-crash' $watch 330
    $seconds=$watch.Elapsed.TotalSeconds
    @{acceptance='actual-supervisor-repeat-trigger-recovery';result=($(if ($seconds -le 300) {'passed'} else {'exceeded-300-seconds'}));actualRecoverySeconds=$seconds;repeatSeconds=300;oldSupervisor=$job.wrapperPid;newSupervisor=(Read-Job).wrapperPid;oldInstance=$before.instanceId;newInstance=$script:Recovered.instanceId;manualStart=$false} | ConvertTo-Json -Compress
    if ($seconds -gt 300) { throw 'Actual recovery exceeded the requested five-minute acceptance window.' }
}
if ($Action -in @('RecoveryAll','Maintenance')) {
    $before=Assert-Running
    $backup=Join-Path 'E:\Backup\ops-agent-deploy-backups' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'-maintenance-check')
    & $python -B $helper prepare --source $agentRoot --target $agentRoot --backup $backup --commit $expected
    if ($LASTEXITCODE) { throw 'Maintenance test source backup failed.' }
    # Cleanup is a one-command rollback; it clears only this backup request.
    $rollback=@'
$ErrorActionPreference='Stop'
$python=Join-Path $env:LOCALAPPDATA 'TikHubOPS\venv_cuda\Scripts\python.exe'
& $python -B (Join-Path $PSScriptRoot 'agent_source_update.py') finish --backup $PSScriptRoot
if ($LASTEXITCODE) { throw 'Owned maintenance cleanup refused.' }
Start-ScheduledTask -TaskName OpsConsoleReadonlyAgent -TaskPath '\'
'@
    $rollback | Set-Content -LiteralPath (Join-Path $backup 'rollback.ps1') -Encoding utf8
    Write-Output ('Maintenance backup: '+$backup)
    Write-Output ('Maintenance rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $backup 'rollback.ps1')+'"')
    $maintenanceStart=[DateTime]::UtcNow.ToFileTimeUtc()
    $watch=[Diagnostics.Stopwatch]::StartNew();Write-Evidence 'maintenance-before'
    & $python -B $helper request-stop --backup $backup
    if ($LASTEXITCODE) { throw 'Owned maintenance request refused.' }
    & $python -B $helper wait --backup $backup
    if ($LASTEXITCODE) { throw 'Maintenance stop not confirmed.' }
    $blocked=$false
    while ($watch.Elapsed.TotalSeconds -lt 330) {
        Write-Evidence 'maintenance-wait-for-real-repeat-trigger'
        $runtime=Read-Agent;$job=Read-Job
        if ($runtime.instanceId -ne $before.instanceId) { throw 'A Python instance started under maintenance; markers retained.' }
        $info=Get-ScheduledTaskInfo -TaskName $taskName -TaskPath '\'
        if ($job.phase -eq 'maintenance-blocked' -and $job.launcherPid -eq 0 -and $job.wrapperCreationFileTime -gt $maintenanceStart -and -not (Test-AgentAlive $runtime) -and $info.LastRunTime.ToUniversalTime().ToFileTimeUtc() -gt $maintenanceStart -and $info.LastTaskResult -eq 0 -and (Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -ne 'Running') { $blocked=$true;break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $blocked) { throw 'No real repeat-trigger maintenance block observed; markers and cleanup rollback retained.' }
    @{acceptance='actual-repeat-trigger-maintenance-block';result='passed';observedSeconds=$watch.Elapsed.TotalSeconds;blockedSupervisor=$job.wrapperPid;pythonStarted=$false;instanceUnchanged=$true;maintenanceKeptUntilObserved=$true} | ConvertTo-Json -Compress
    & $python -B $helper finish --backup $backup
    if ($LASTEXITCODE) { throw 'Maintenance ownership changed; no start requested.' }
    Write-Output 'Explicit manual start after completed maintenance test; not automatic recovery.'
    Start-ScheduledTask -TaskName $taskName -TaskPath '\'
    $watch=[Diagnostics.Stopwatch]::StartNew()
    # This stage is explicitly manual and must not be labelled automatic.
    Wait-Recovery $before $job.wrapperPid 'manual-after-maintenance' $watch 30
    Write-Evidence 'maintenance-cleanup-complete'
}
