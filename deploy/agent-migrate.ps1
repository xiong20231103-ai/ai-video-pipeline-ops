param(
    [ValidateSet('Install','Rollback')][string]$Action='Install',
    [string]$SourcePackage,
    [string]$ExpectedCommit,
    [string]$BackupPath
)
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'One-time migration needs Administrator PowerShell to replace the legacy task and grant this user execute access.' }
$taskName='OpsConsoleReadonlyAgent';$agentRoot='E:\Backup\ops-agent'
$python=Join-Path $env:LOCALAPPDATA 'TikHubOPS\venv_cuda\Scripts\python.exe'
$state=Join-Path $env:LOCALAPPDATA 'OpsAgent'
$helper=Join-Path $PSScriptRoot 'agent_source_update.py'
$legacy=Join-Path $PSScriptRoot 'agent_legacy_lock.py'
if ($Action -eq 'Rollback') { $helper=Join-Path $BackupPath 'agent_source_update.py';$legacy=Join-Path $BackupPath 'agent_legacy_lock.py' }
$task=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
if ($task.Description -ne 'OPS Console read-only agent; owned task; no production program control.' -or $task.Actions.Count -ne 1 -or $task.Actions[0].WorkingDirectory.TrimEnd('\') -ne $agentRoot) { throw 'Owned task identity mismatch.' }
$basePython=& $python -B -c 'import sys;print(sys._base_executable)'
if ($LASTEXITCODE -ne 0) { throw 'Existing interpreter unavailable; no packages installed.' }
$allowedExecutables=@($python.Trim(),$basePython.Trim())
$escapedPaths=($allowedExecutables | ForEach-Object { [Regex]::Escape($_) }) -join '|'
$launcherPattern='^(?:"(?:'+$escapedPaths+')"|(?:'+$escapedPaths+'))\s+-B\s+-m\s+agent\.launcher\s*$'
$ownerSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function Get-VerifiedLegacyOwners {
    $raw=& $python -B $legacy
    if ($LASTEXITCODE -ne 0) { throw 'Cannot identify legacy lock holders; no process terminated.' }
    $owners=@($raw | ConvertFrom-Json)
    foreach ($holder in $owners) {
        $process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$holder.pid)
        if (-not $process -or $process.CommandLine -notmatch $launcherPattern -or $process.ExecutablePath -notin $allowedExecutables) { throw 'Unexpected lock holder; no process terminated.' }
        $owner=Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid
        if ($owner.ReturnValue -ne 0 -or $owner.Sid -ne $ownerSid) { throw 'Legacy process owner mismatch; no process terminated.' }
        $born=(Get-Process -Id $holder.pid).StartTime.ToUniversalTime().ToFileTimeUtc()
        if ([Int64]$born -ne [Int64]$holder.processCreationFileTime) { throw 'Legacy process identity changed; no process terminated.' }
    }
    return $owners
}
$inspection=& $python -B $helper inspect --target $agentRoot
if ($LASTEXITCODE -ne 0) { throw 'Installed source validation failed.' }
$supportsStop=($inspection | ConvertFrom-Json).supportsGracefulStop
if (-not $supportsStop) { $null=Get-VerifiedLegacyOwners } # Validate every holder before any task change.
$service=New-Object -ComObject 'Schedule.Service';$service.Connect()
if ($Action -eq 'Install') {
    if ($ExpectedCommit -notmatch '^[a-f0-9]{40}$') { throw 'Reviewed commit required.' }
    $BackupPath=Join-Path 'E:\Backup\ops-agent-deploy-backups' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'-lifecycle-migration')
    & $python -B $helper prepare --source $SourcePackage --target $agentRoot --backup $BackupPath --commit $ExpectedCommit
    if ($LASTEXITCODE -ne 0) { throw 'Source backup failed; task unchanged.' }
    Export-ScheduledTask -TaskName $taskName -TaskPath '\' | Set-Content -LiteralPath (Join-Path $BackupPath 'task-before.xml') -Encoding Unicode
    $service.GetFolder('\').GetTask($taskName).GetSecurityDescriptor(7) | Set-Content -LiteralPath (Join-Path $BackupPath 'task-before-sddl.txt') -Encoding utf8
    @{enabled=[bool]$task.Settings.Enabled} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $BackupPath 'task-before-state.json') -Encoding utf8
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $BackupPath 'agent-migrate.ps1')
    Copy-Item -LiteralPath $legacy -Destination (Join-Path $BackupPath 'agent_legacy_lock.py')
    "& (Join-Path `$PSScriptRoot 'agent-migrate.ps1') -Action Rollback -BackupPath `$PSScriptRoot" | Set-Content -LiteralPath (Join-Path $BackupPath 'rollback.ps1') -Encoding utf8
}
Write-Output "Migration backup: $BackupPath"
Write-Output ('Migration rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $BackupPath 'rollback.ps1')+'"')
# One-time task migration only. Routine updates never disable/stop tasks.
Disable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
if ($supportsStop) {
    & $python -B $helper request-stop --target $agentRoot --backup $BackupPath
    if ($LASTEXITCODE -ne 0) { throw 'Stop request refused; rollback retained.' }
    & $python -B $helper wait --target $agentRoot --backup $BackupPath
    if ($LASTEXITCODE -ne 0) { throw 'Cooperative stop not confirmed; no source replacement.' }
} else {
    # Legacy code cannot read stop files. Only exact file-holder PID+creation,
    # current-user SID, interpreter path and complete launcher argv can qualify.
    foreach ($holder in @(Get-VerifiedLegacyOwners)) {
        Write-Output ('One-time legacy agent exit: PID='+$holder.pid+' creationFileTime='+$holder.processCreationFileTime)
        & $python -B $legacy $holder.pid $holder.processCreationFileTime
        if ($LASTEXITCODE -ne 0) { throw 'Legacy identity/exit not confirmed; no source replacement.' }
    }
}
& $python -B $helper probe
if ($LASTEXITCODE -ne 0) { throw 'Agent lock still held; no source replacement.' }
for ($attempt=0;$attempt -lt 100;$attempt++) {
    if ((Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -ne 'Running') { break }
    Start-Sleep -Milliseconds 100
}
if ((Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -eq 'Running') { throw 'Legacy wrapper did not exit; no source replacement.' }
if ($Action -eq 'Install') {
    & $python -B $helper bootstrap --source $SourcePackage --target $agentRoot --backup $BackupPath --commit $ExpectedCommit
    if ($LASTEXITCODE -ne 0) { throw 'Pinned source migration failed; use printed rollback.' }
    & (Join-Path $agentRoot 'deploy\agent-task.ps1') -Action Install -AgentRoot $agentRoot -PythonExecutable $python
} else {
    & $python -B $helper bootstrap-restore --target $agentRoot --backup $BackupPath
    if ($LASTEXITCODE -ne 0) { throw 'Pinned source restore failed.' }
    Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Xml ([IO.File]::ReadAllText((Join-Path $BackupPath 'task-before.xml'))) -Force | Out-Null
    $service.GetFolder('\').GetTask($taskName).SetSecurityDescriptor([IO.File]::ReadAllText((Join-Path $BackupPath 'task-before-sddl.txt')),16)
}
& $python -B $helper finish --target $agentRoot --backup $BackupPath
if ($LASTEXITCODE -ne 0) { throw 'Maintenance ownership changed; task not started.' }
$previousInstance=$null
$runtimePath=Join-Path $state 'agent-runtime.json'
if (Test-Path -LiteralPath $runtimePath) { $previousInstance=(Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json).instanceId }
$shouldStart=$true
if ($Action -eq 'Rollback') { $shouldStart=(Get-Content -LiteralPath (Join-Path $BackupPath 'task-before-state.json') -Raw | ConvertFrom-Json).enabled }
if ($shouldStart) { Enable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null;Start-ScheduledTask -TaskName $taskName -TaskPath '\' }
if ($Action -eq 'Install' -and $shouldStart) {
    $started=$false
    for ($attempt=0;$attempt -lt 200;$attempt++) {
        if (Test-Path -LiteralPath $runtimePath) {
            $runtime=Get-Content -LiteralPath $runtimePath -Raw | ConvertFrom-Json
            if ($runtime.instanceId -ne $previousInstance -and $runtime.version -eq $ExpectedCommit -and $runtime.phase -eq 'running' -and (Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -eq 'Running') { $started=$true;break }
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $started) { throw 'Migration files/task installed but running instance not confirmed; use printed rollback or inspect status.' }
    $runtime | Select-Object instanceId,pid,parentPid,version,phase,observedAt | ConvertTo-Json -Compress | Write-Output
}
Write-Output 'One-time task/source migration completed; private credentials were not read or changed.'
Get-ScheduledTask -TaskName $taskName -TaskPath '\' | Select-Object TaskName,State
