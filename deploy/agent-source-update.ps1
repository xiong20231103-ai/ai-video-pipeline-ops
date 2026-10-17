param(
    [ValidateSet('Update','Rollback')][string]$Action='Update',
    [string]$SourcePackage,
    [string]$ExpectedCommit,
    [string]$BackupPath
)
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run in Administrator PowerShell; Windows task ACL requires elevation.' }
$taskName='OpsConsoleReadonlyAgent'
$agentRoot='E:\Backup\ops-agent'
$python=Join-Path $env:LOCALAPPDATA 'TikHubOPS\venv_cuda\Scripts\python.exe'
$helper=Join-Path $PSScriptRoot 'agent_source_update.py'
$task=Get-ScheduledTask -TaskName $taskName -TaskPath '\'
if ($task.Description -ne 'OPS Console read-only agent; owned task; no production program control.') { throw 'Task ownership mismatch.' }
if ($task.Actions.Count -ne 1 -or $task.Actions[0].WorkingDirectory.TrimEnd('\') -ne $agentRoot) { throw 'Task action mismatch.' }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Existing Python missing; no packages installed.' }
if ($Action -eq 'Update') {
    if (-not $ExpectedCommit -or $ExpectedCommit -notmatch '^[a-f0-9]{40}$') { throw 'Expected commit required.' }
    $BackupPath=Join-Path 'E:\Backup\ops-agent-deploy-backups' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'-source-update')
    & $python -B $helper prepare --source $SourcePackage --target $agentRoot --backup $BackupPath --commit $ExpectedCommit
    if ($LASTEXITCODE -ne 0) { throw 'Code preparation failed; task unchanged.' }
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $BackupPath 'agent-source-update.ps1')
    Export-ScheduledTask -TaskName $taskName -TaskPath '\' | Set-Content -LiteralPath (Join-Path $BackupPath 'task-before.xml') -Encoding Unicode
    "& (Join-Path `$PSScriptRoot 'agent-source-update.ps1') -Action Rollback -BackupPath `$PSScriptRoot" | Set-Content -LiteralPath (Join-Path $BackupPath 'rollback.ps1') -Encoding utf8
    Write-Output "Backup: $BackupPath"
    Write-Output ('Rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $BackupPath 'rollback.ps1')+'"')
} else {
    if (-not (Test-Path -LiteralPath (Join-Path $BackupPath 'operation.json'))) { throw 'Completed source backup required.' }
    $helper=Join-Path $BackupPath 'agent_source_update.py'
}
# Backups and a complete rollback exist before the only task is paused.
$paused=$false
try {
    Disable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
    $paused=$true
    Stop-ScheduledTask -TaskName $taskName -TaskPath '\'
    $lockFree=$false
    for ($attempt=0;$attempt -lt 20;$attempt++) {
        & $python -B $helper probe
        if ($LASTEXITCODE -eq 0) { $lockFree=$true;break }
        Start-Sleep -Seconds 1
    }
    if (-not $lockFree) { throw 'Agent lock still held; no code replacement performed. No process was killed by name.' }
    if ($Action -eq 'Update') {
        & $python -B $helper apply --source $SourcePackage --target $agentRoot --backup $BackupPath --commit $ExpectedCommit
    } else {
        & $python -B $helper restore --target $agentRoot --backup $BackupPath
    }
    if ($LASTEXITCODE -ne 0) { throw 'Source operation failed; inspect private backup, do not reconfigure credentials.' }
} finally {
    if ($paused) {
        Enable-ScheduledTask -TaskName $taskName -TaskPath '\' | Out-Null
        Start-ScheduledTask -TaskName $taskName -TaskPath '\'
    }
}
Write-Output 'Verified code operation complete; only the owned read-only agent task was restarted.'
