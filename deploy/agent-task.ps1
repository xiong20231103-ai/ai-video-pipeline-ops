param(
    [ValidateSet('Plan','Install','Rollback')][string]$Action = 'Plan',
    [string]$AgentRoot = 'E:\Backup\ops-agent',
    [string]$PythonExecutable = (Join-Path $env:LOCALAPPDATA 'TikHubOPS\venv_cuda\Scripts\python.exe'),
    [string]$BackupPath,
    [switch]$StartNow
)
$ErrorActionPreference = 'Stop'
$script:AgentTaskName = 'OpsConsoleReadonlyAgent'
$script:AgentTaskPath = '\'
$script:AgentTaskDescription = 'OPS Console read-only agent; owned task; no production program control.'

function New-AgentTaskDefinition {
    param([string]$Root,[string]$Python)
    if ($Root.Contains('"') -or $Python.Contains('"')) { throw 'Invalid path quoting.' }
    $taskUser = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $taskRunner = [IO.Path]::Combine($Root,'deploy\agent-run.ps1')
    $taskArguments = '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $taskRunner + '" -AgentRoot "' + $Root + '" -PythonExecutable "' + $Python + '"'
    $taskAction = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Argument $taskArguments -WorkingDirectory $Root
    $taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
    # One task: immediate logon plus an indefinite five-minute interactive-session watchdog.
    $taskWatchdog = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(5)) -RepetitionInterval (New-TimeSpan -Minutes 5)
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet -Hidden -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    return New-ScheduledTask -Action $taskAction -Trigger @($taskTrigger,$taskWatchdog) -Principal $taskPrincipal -Settings $taskSettings -Description $script:AgentTaskDescription
}

function Get-AgentTaskSecurityDescriptor {
    $taskService=New-Object -ComObject 'Schedule.Service';$taskService.Connect()
    return $taskService.GetFolder('\').GetTask($script:AgentTaskName).GetSecurityDescriptor(7)
}
function Set-AgentTaskSecurityDescriptor {
    param([string]$Descriptor)
    $taskService=New-Object -ComObject 'Schedule.Service';$taskService.Connect()
    $taskService.GetFolder('\').GetTask($script:AgentTaskName).SetSecurityDescriptor($Descriptor,16)
}
function Set-AgentTaskUserExecuteAccess {
    $taskSecurity=New-Object Security.AccessControl.RawSecurityDescriptor((Get-AgentTaskSecurityDescriptor))
    $taskSid=[Security.Principal.WindowsIdentity]::GetCurrent().User
    $taskAce=New-Object Security.AccessControl.CommonAce([Security.AccessControl.AceFlags]::None,[Security.AccessControl.AceQualifier]::AccessAllowed,0x1200a9,$taskSid,$false,$null)
    $taskSecurity.DiscretionaryAcl.InsertAce(0,$taskAce)
    Set-AgentTaskSecurityDescriptor -Descriptor $taskSecurity.GetSddlForm([Security.AccessControl.AccessControlSections]::All)
}

function Invoke-AgentTask {
    param([string]$Operation,[string]$Root,[string]$Python,[string]$Backup,[bool]$Start)
    if ($Operation -eq 'Plan') { return New-AgentTaskDefinition -Root $Root -Python $Python }
    if ($Operation -eq 'Rollback') {
        $taskBackup = (Resolve-Path -LiteralPath $Backup).Path
        if (-not (Test-Path -LiteralPath (Join-Path $taskBackup 'backup-complete.json'))) { throw 'No completed agent-task backup found.' }
        $taskCurrent = Get-ScheduledTask -TaskName $script:AgentTaskName -TaskPath $script:AgentTaskPath -ErrorAction SilentlyContinue
        if ($taskCurrent -and $taskCurrent.Description -ne $script:AgentTaskDescription) { throw 'Task ownership changed; refusing to touch it.' }
        if ($taskCurrent) {
            Stop-ScheduledTask -TaskName $script:AgentTaskName -TaskPath $script:AgentTaskPath -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $script:AgentTaskName -TaskPath $script:AgentTaskPath -Confirm:$false
        }
        $taskOldXml = Join-Path $taskBackup 'previous-task.xml'
        if (Test-Path -LiteralPath $taskOldXml) {
            Register-ScheduledTask -TaskName $script:AgentTaskName -TaskPath $script:AgentTaskPath -Xml ([IO.File]::ReadAllText($taskOldXml)) -Force | Out-Null
            $taskOldSddl=Join-Path $taskBackup 'previous-task-sddl.txt'
            if (Test-Path -LiteralPath $taskOldSddl) { Set-AgentTaskSecurityDescriptor -Descriptor ([IO.File]::ReadAllText($taskOldSddl)) }
        }
        Write-Output 'Agent task rolled back. Agent files/config retained; no other task or production program touched.'
        return
    }
    if ($Operation -ne 'Install') { throw 'Unsupported operation.' }
    $taskRoot = (Resolve-Path -LiteralPath $Root).Path
    if ($taskRoot.TrimEnd('\') -ne 'E:\Backup\ops-agent') { throw 'Installation is restricted to the independent agent directory.' }
    foreach ($taskFile in @($Python,([IO.Path]::Combine($taskRoot,'agent\readonly.py')),([IO.Path]::Combine($taskRoot,'agent\lifecycle.py')),([IO.Path]::Combine($taskRoot,'deploy\AgentJobRunner.cs')),([IO.Path]::Combine($taskRoot,'deploy\agent-run.ps1')),(Join-Path $env:LOCALAPPDATA 'OpsAgent\config.json'))) {
        if (-not (Test-Path -LiteralPath $taskFile -PathType Leaf)) { throw 'Runtime or private configuration missing; no task changed.' }
    }
    $taskExisting = Get-ScheduledTask -TaskName $script:AgentTaskName -TaskPath $script:AgentTaskPath -ErrorAction SilentlyContinue
    if ($taskExisting -and $taskExisting.Description -ne $script:AgentTaskDescription) { throw 'Existing task is not owned by this project.' }
    if ($taskExisting -and $taskExisting.State -eq 'Running') { throw 'Agent already running; stop only its own task in an approved maintenance window before replacement.' }
    if (-not $Backup) { $Backup = Join-Path 'E:\Backup\ops-agent-task-backups' ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)) }
    if (Test-Path -LiteralPath $Backup) { throw 'Backup directory already exists; refusing overwrite.' }
    $taskBackup = [IO.Directory]::CreateDirectory($Backup).FullName
    $taskAcl = Get-Acl -LiteralPath $taskBackup
    $taskAcl.SetAccessRuleProtection($true,$false)
    foreach ($taskSid in @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value,'S-1-5-18','S-1-5-32-544')) {
        $taskIdentity = New-Object Security.Principal.SecurityIdentifier($taskSid)
        $taskRule = New-Object Security.AccessControl.FileSystemAccessRule($taskIdentity,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $taskAcl.AddAccessRule($taskRule)
    }
    Set-Acl -LiteralPath $taskBackup -AclObject $taskAcl
    if ($taskExisting) {
        Export-ScheduledTask -TaskName $script:AgentTaskName -TaskPath $script:AgentTaskPath | Set-Content -LiteralPath (Join-Path $taskBackup 'previous-task.xml') -Encoding Unicode
        Get-AgentTaskSecurityDescriptor | Set-Content -LiteralPath (Join-Path $taskBackup 'previous-task-sddl.txt') -Encoding utf8
    }
    Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $taskBackup 'agent-task.ps1')
    $taskRollback = '& (Join-Path $PSScriptRoot ''agent-task.ps1'') -Action Rollback -BackupPath $PSScriptRoot'
    $taskRollback | Set-Content -LiteralPath (Join-Path $taskBackup 'rollback.ps1') -Encoding utf8
    @{ taskName=$script:AgentTaskName; previousTask=[bool]$taskExisting; observedAt=[DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBackup 'backup-complete.json') -Encoding utf8
    # All backup artifacts and one-command rollback exist before registration.
    $taskDefinition = New-AgentTaskDefinition -Root $taskRoot -Python $Python
    Register-ScheduledTask -TaskName $script:AgentTaskName -TaskPath $script:AgentTaskPath -InputObject $taskDefinition -Force | Out-Null
    Set-AgentTaskUserExecuteAccess
    Write-Output "Backup: $taskBackup"
    Write-Output ('Rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $taskBackup 'rollback.ps1') + '"')
    if ($Start) { Start-ScheduledTask -TaskName $script:AgentTaskName -TaskPath $script:AgentTaskPath }
}

if ($MyInvocation.InvocationName -ne '.') {
    Invoke-AgentTask -Operation $Action -Root $AgentRoot -Python $PythonExecutable -Backup $BackupPath -Start ([bool]$StartNow)
}
