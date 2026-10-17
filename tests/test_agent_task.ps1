$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\deploy\agent-task.ps1')
$taskDefinition = New-AgentTaskDefinition -Root 'E:\Backup\ops-agent' -Python 'C:\fixture\python.exe'
function Assert-TaskValue([bool]$Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
Assert-TaskValue ($taskDefinition.Triggers.Count -eq 1) 'Exactly one logon trigger required.'
Assert-TaskValue ($taskDefinition.Triggers[0].CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger') 'Must start after user logon.'
Assert-TaskValue ($taskDefinition.Actions.Count -eq 1) 'Exactly one owned action required.'
Assert-TaskValue ($taskDefinition.Actions[0].Arguments -like '*-WindowStyle Hidden*agent-run.ps1*') 'Hidden wrapper required.'
Assert-TaskValue ($taskDefinition.Settings.MultipleInstances -eq 2) 'IgnoreNew single instance required.'
Assert-TaskValue ($taskDefinition.Settings.RestartCount -eq 999) 'Crash restart required.'
Assert-TaskValue ($taskDefinition.Settings.RestartInterval -eq 'PT1M') 'One minute restart delay required.'
Assert-TaskValue ($taskDefinition.Settings.ExecutionTimeLimit -eq 'PT0S') 'Agent must not expire after default 72 hours.'
Assert-TaskValue ([bool]$taskDefinition.Settings.Hidden) 'Task must be hidden.'
Assert-TaskValue ($taskDefinition.Principal.LogonType -eq 3) 'Interactive token; no stored logon password.'
Assert-TaskValue ($taskDefinition.Principal.RunLevel -eq 0) 'No elevated task privileges.'
$taskTokens=$null; $taskErrors=$null
foreach ($taskFile in @('agent-task.ps1','agent-run.ps1')) {
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot "..\deploy\$taskFile"),[ref]$taskTokens,[ref]$taskErrors)
    Assert-TaskValue ($taskErrors.Count -eq 0) "PowerShell parser errors in $taskFile"
}
# Exercise install/rollback with mocked task registry and private-config existence.
# These functions shadow the cmdlets only in this test process; no task is registered.
$script:FixtureTask = $null
$script:RegisterCalls = 0
$script:StopCalls = 0
$script:UnregisterCalls = 0
$script:FixtureXml = '<Task><Fixture>previous-owned-task</Fixture></Task>'
function Resolve-Path {
    param([string]$LiteralPath)
    if ($LiteralPath -eq 'E:\Backup\ops-agent') { return [pscustomobject]@{Path=$LiteralPath} }
    Microsoft.PowerShell.Management\Resolve-Path -LiteralPath $LiteralPath
}
function Test-Path {
    param([string]$LiteralPath,[string]$PathType)
    if ($LiteralPath -eq 'C:\fixture\python.exe' -or $LiteralPath -like 'E:\Backup\ops-agent\*' -or $LiteralPath -like '*\OpsAgent\config.json') { return $true }
    if ($PathType) { return Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath -PathType $PathType }
    Microsoft.PowerShell.Management\Test-Path -LiteralPath $LiteralPath
}
function Get-ScheduledTask { [CmdletBinding()]param($TaskName,$TaskPath) return $script:FixtureTask }
function Export-ScheduledTask { param($TaskName,$TaskPath) return $script:FixtureXml }
function Register-ScheduledTask {
    param($TaskName,$TaskPath,$InputObject,$Xml,[switch]$Force)
    Assert-TaskValue ($TaskName -eq 'OpsConsoleReadonlyAgent' -and $TaskPath -eq '\') 'Foreign task mutation attempted.'
    $script:RegisterCalls++
    $script:FixtureTask=[pscustomobject]@{Description=$script:AgentTaskDescription;State='Ready';RestoredXml=$Xml}
}
function Stop-ScheduledTask { [CmdletBinding()]param($TaskName,$TaskPath) $script:StopCalls++ }
function Unregister-ScheduledTask { param($TaskName,$TaskPath,[bool]$Confirm) $script:UnregisterCalls++; $script:FixtureTask=$null }
function Start-ScheduledTask { param($TaskName,$TaskPath) throw 'Test must never start an agent.' }
$taskScratch = Join-Path ([IO.Path]::GetTempPath()) ('ops-agent-task-test-' + [Guid]::NewGuid().ToString('N'))
$taskFirstBackup=Join-Path $taskScratch 'first'
Invoke-AgentTask -Operation Install -Root 'E:\Backup\ops-agent' -Python 'C:\fixture\python.exe' -Backup $taskFirstBackup -Start $false
Assert-TaskValue ($script:RegisterCalls -eq 1) 'Install should register only once.'
Assert-TaskValue (Test-Path -LiteralPath (Join-Path $taskFirstBackup 'rollback.ps1')) 'Rollback must exist before registration.'
Assert-TaskValue ((Get-FileHash -LiteralPath (Join-Path $taskFirstBackup 'agent-task.ps1')).Hash -eq (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot '..\deploy\agent-task.ps1')).Hash) 'Backup must contain the installer itself.'
Invoke-AgentTask -Operation Rollback -Backup $taskFirstBackup
Assert-TaskValue ($null -eq $script:FixtureTask) 'Fresh install rollback should remove only owned task.'
Assert-TaskValue ($script:StopCalls -eq 1 -and $script:UnregisterCalls -eq 1) 'Rollback should stop/unregister only once.'
$script:FixtureTask=[pscustomobject]@{Description=$script:AgentTaskDescription;State='Ready'}
$taskSecondBackup=Join-Path $taskScratch 'second'
Invoke-AgentTask -Operation Install -Root 'E:\Backup\ops-agent' -Python 'C:\fixture\python.exe' -Backup $taskSecondBackup -Start $false
Invoke-AgentTask -Operation Rollback -Backup $taskSecondBackup
Assert-TaskValue ($script:FixtureTask.RestoredXml.Trim() -eq $script:FixtureXml) 'Prior task XML must be restored exactly.'
$script:FixtureTask=[pscustomobject]@{Description='unrelated-task';State='Ready'}
$taskRejected=$false
try { Invoke-AgentTask -Operation Rollback -Backup $taskSecondBackup } catch { $taskRejected=$true }
Assert-TaskValue $taskRejected 'Ownership collision must fail closed.'
Write-Output 'PASS: task definition, syntax, mocked install/rollback, previous XML restore, ownership collision; no real task registered or agent started.'
