param(
    [ValidateSet('Update','Rollback')][string]$Action='Update',
    [string]$SourcePackage,
    [string]$ExpectedCommit,
    [string]$BackupPath
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'agent-json.ps1')
$taskName='OpsConsoleReadonlyAgent'
$agentRoot='E:\Backup\ops-agent'
$python=Join-Path $env:LOCALAPPDATA 'TikHubOPS\venv_cuda\Scripts\python.exe'
$state=Join-Path $env:LOCALAPPDATA 'OpsAgent'
$helper=Join-Path $PSScriptRoot 'agent_source_update.py'
if ($Action -eq 'Rollback') { $helper=Join-Path $BackupPath 'agent_source_update.py' }
$task=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
if ($task.Description -ne 'OPS Console read-only agent; owned task; no production program control.') { throw 'Task ownership mismatch.' }
if ($task.Actions.Count -ne 1 -or $task.Actions[0].WorkingDirectory.TrimEnd('\') -ne $agentRoot) { throw 'Task action mismatch.' }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Existing Python missing; nothing installed.' }
# Explicit execute access for this exact user is installed once by agent-task.ps1.
# Routine updates never modify task ACL/settings or stop/disable the task.
$service=New-Object -ComObject 'Schedule.Service';$service.Connect()
$registered=$service.GetFolder('\').GetTask($taskName)
$descriptor=New-Object Security.AccessControl.RawSecurityDescriptor($registered.GetSecurityDescriptor(7))
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
$canExecute=$false
foreach ($ace in $descriptor.DiscretionaryAcl) {
    if ($ace.SecurityIdentifier -eq $sid -and $ace.AceQualifier -eq 'AccessAllowed' -and ($ace.AccessMask -band 32)) { $canExecute=$true }
    if ($ace.SecurityIdentifier -eq $sid -and $ace.AceQualifier -eq 'AccessDenied' -and ($ace.AccessMask -band 32)) { throw 'Task execution denied for current user.' }
}
if (-not $canExecute) { throw 'One-time task migration required to grant this user read/execute access; no update started.' }
function Invoke-AgentTool {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Items)
    $arguments=@('-B',$helper)+$Items
    foreach($value in $arguments){if($value.Contains('"') -or $value.Contains("`n") -or $value.Contains("`r") -or $value.EndsWith('\')){throw 'Unsafe helper argument.'}}
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$python;$psi.Arguments=($arguments|ForEach-Object{'"'+$_+'"'}) -join ' '
    $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
    $psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $child=New-Object Diagnostics.Process;$child.StartInfo=$psi
    try{
        [void]$child.Start();$out=$child.StandardOutput.ReadToEndAsync();$err=$child.StandardError.ReadToEndAsync();$child.WaitForExit()
        $script:LASTEXITCODE=$child.ExitCode
        $stdout=$out.GetAwaiter().GetResult();$stderr=$err.GetAwaiter().GetResult()
    }finally{$child.Dispose()}
    # The helper emits only bounded sanitized metadata; never invoke a shell.
    if($stdout){Write-Output $stdout.TrimEnd()}
    if($stderr){Write-Output 'Agent helper reported an error; private configuration was not read or logged.'}
}
$inspection=Invoke-AgentTool inspect --target $agentRoot
if ($LASTEXITCODE -ne 0) { throw 'Installed source validation failed.' }
if (-not ($inspection | ConvertFrom-Json).supportsGracefulStop) { throw 'Legacy agent requires one-time migration while its lock is free; no process was killed.' }
$previousInstance=$null
$runtimePath=Join-Path $state 'agent-runtime.json'
if (Test-Path -LiteralPath $runtimePath) { $previousInstance=(Read-SharedJson -Path $runtimePath).instanceId }
if ($Action -eq 'Update') {
    if ($ExpectedCommit -notmatch '^[a-f0-9]{40}$') { throw 'Expected commit required.' }
    $BackupPath=Join-Path 'E:\Backup\ops-agent-deploy-backups' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'-graceful-update')
    Invoke-AgentTool prepare --source $SourcePackage --target $agentRoot --backup $BackupPath --commit $ExpectedCommit
    if ($LASTEXITCODE -ne 0) { throw 'Code preparation failed; no stop requested.' }
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $BackupPath 'agent-source-update.ps1')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'agent-json.ps1') -Destination (Join-Path $BackupPath 'agent-json.ps1')
    Export-ScheduledTask -TaskName $taskName -TaskPath '\' | Set-Content -LiteralPath (Join-Path $BackupPath 'task-before.xml') -Encoding Unicode
    "& (Join-Path `$PSScriptRoot 'agent-source-update.ps1') -Action Rollback -BackupPath `$PSScriptRoot" | Set-Content -LiteralPath (Join-Path $BackupPath 'rollback.ps1') -Encoding utf8
    Write-Output "Backup: $BackupPath"
    Write-Output ('Rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $BackupPath 'rollback.ps1')+'"')
}
Invoke-AgentTool request-stop --target $agentRoot --backup $BackupPath
if ($LASTEXITCODE -ne 0) { throw 'Stop request refused; source unchanged.' }
Invoke-AgentTool wait --target $agentRoot --backup $BackupPath
if ($LASTEXITCODE -ne 0) { throw 'Graceful stop not confirmed; source unchanged, maintenance retained. No process was killed.' }
for ($attempt=0;$attempt -lt 100;$attempt++) {
    if ((Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -ne 'Running') { break }
    Start-Sleep -Milliseconds 100
}
if ((Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -eq 'Running') { throw 'Task wrapper did not exit; source unchanged.' }
if ($Action -eq 'Update') {
    Invoke-AgentTool apply --source $SourcePackage --target $agentRoot --backup $BackupPath --commit $ExpectedCommit
} else {
    Invoke-AgentTool restore --target $agentRoot --backup $BackupPath
}
if ($LASTEXITCODE -ne 0) { throw 'Source replacement failed; maintenance retained for recovery.' }
Invoke-AgentTool finish --target $agentRoot --backup $BackupPath
if ($LASTEXITCODE -ne 0) { throw 'Maintenance identity changed; no task started.' }
$expectedVersion=if ($Action -eq 'Update') { $ExpectedCommit } else { (Read-SharedJson -Path (Join-Path $BackupPath 'operation.json')).before }
Start-ScheduledTask -TaskName $taskName -TaskPath '\'
$started=$false
for ($attempt=0;$attempt -lt 150;$attempt++) {
    if (Test-Path -LiteralPath $runtimePath) {
        $runtime=Read-SharedJson -Path $runtimePath
        if ($runtime.instanceId -ne $previousInstance -and $runtime.phase -eq 'running' -and $runtime.version -eq $expectedVersion -and (Get-ScheduledTask -TaskName $taskName -TaskPath '\').State -eq 'Running') { $started=$true;break }
    }
    Start-Sleep -Milliseconds 100
}
if (-not $started) { throw 'Task start requested but a new agent instance was not confirmed; inspect lifecycle status, do not re-enter credentials.' }
Write-Output ('New agent PID: '+$runtime.pid+'; version: '+$runtime.version+'; phase: '+$runtime.phase)
Write-Output 'Verified cooperative stop -> free lock -> source update -> new agent start. No administrator elevation or task stop was used.'
