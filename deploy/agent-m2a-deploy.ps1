param(
    [ValidateSet('Deploy','Rollback')][string]$Action='Deploy',
    [string]$SourcePackage,
    [string]$ExpectedCommit,
    [string]$ExpectedInstalledCommit,
    [string]$ExpectedManifestSHA256,
    [string]$ExpectedToolsManifestSHA256,
    [string]$OperationFile,
    [string]$EvidenceDirectory='E:\Backup\Documents\ChatGPT\New project 3\implementation-tools\m2a-evidence'
)
$ErrorActionPreference='Stop'
$agentRoot='E:\Backup\ops-agent'
$stateRoot=Join-Path $env:LOCALAPPDATA 'OpsAgent'
$python=Join-Path $env:LOCALAPPDATA 'TikHubOPS\venv_cuda\Scripts\python.exe'
$backupRoot='E:\Backup\ops-agent-deploy-backups'
$keyPath=Join-Path $env:USERPROFILE '.ssh\ops_m0_120_26_31_102'
$workspaceRoot='E:\Backup\Documents\ChatGPT\New project 3'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Existing Python missing; no packages will be installed.' }
function Invoke-M2aNative {
    param([string]$Executable,[string[]]$Items,[string]$WorkingDirectory)
    foreach($item in $Items){if($item.Contains('"') -or $item.Contains([char]10) -or $item.Contains([char]13) -or $item.EndsWith('\')){throw 'Unsupported native argument.'}}
    $psi=New-Object Diagnostics.ProcessStartInfo
    $psi.FileName=$Executable;$psi.Arguments=($Items|ForEach-Object{'"'+$_+'"'}) -join ' '
    $psi.WorkingDirectory=$WorkingDirectory;$psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.WindowStyle=[Diagnostics.ProcessWindowStyle]::Hidden
    $psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
    $psi.EnvironmentVariables['PSModulePath']='C:\Windows\System32\WindowsPowerShell\v1.0\Modules;C:\Program Files\WindowsPowerShell\Modules'
    $child=New-Object Diagnostics.Process;$child.StartInfo=$psi
    try{[void]$child.Start();$out=$child.StandardOutput.ReadToEndAsync();$err=$child.StandardError.ReadToEndAsync();$child.WaitForExit();$answer=[pscustomobject]@{exitCode=$child.ExitCode;stdout=$out.GetAwaiter().GetResult();stderr=$err.GetAwaiter().GetResult()}}finally{$child.Dispose()}
    $nl=[Environment]::NewLine
    [IO.File]::AppendAllText($script:logPath,('Executable: '+$Executable+$nl+$answer.stdout+$answer.stderr+$nl+'ExitCode: '+$answer.exitCode+$nl))
    if($answer.stdout){Write-Host $answer.stdout.TrimEnd()}
    return $answer
}
function Pause-CloudCommands([string]$Directory,[switch]$CancelQueued){
    $command='if test -f /opt/ops-console/current/cloud/command_admin.py; then cd /opt/ops-console/current && sudo -u ops-console env PYTHONPATH=/opt/ops-console/current .venv/bin/python -B -m cloud.command_admin pause --wait 60'
    if($CancelQueued){$command+=' --cancel-queued'}
    $command+='; else echo Previous-cloud-release-has-no-command-route; fi'
    $items=@('-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes','-o','HostKeyAlias=120.26.31.102','-o','UserKnownHostsFile=known-hosts','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-i',$keyPath,'admin@100.127.112.48',$command)
    $answer=Invoke-M2aNative 'C:\Windows\System32\OpenSSH\ssh.exe' $items $Directory
    if($answer.exitCode){throw 'Cloud pause/drain refused or unreachable; no home source/switch change started.'}
}
if ($Action -eq 'Rollback') {
    if (-not $OperationFile) { throw 'OperationFile required.' }
    $operationPath=[IO.Path]::GetFullPath($OperationFile)
    if(-not $operationPath.StartsWith($backupRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Owned backup path required.'}
    $directory=Split-Path -Parent $operationPath
    $script:logPath=Join-Path $directory ('rollback-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'.txt')
    $operation=Get-Content -LiteralPath $operationPath -Raw | ConvertFrom-Json
    if($operation.schema -ne 1 -or $operation.agentRoot -ne $agentRoot){throw 'Rollback identity mismatch.'}
    $installedNow=Get-Content -LiteralPath (Join-Path $agentRoot 'deployment-manifest.json') -Raw | ConvertFrom-Json
    if(@($operation.before,$operation.after) -notcontains $installedNow.commit){throw 'A newer deployment exists; old rollback refused before changing cloud or agent.'}
    Pause-CloudCommands $directory -CancelQueued
    if(Test-Path -LiteralPath (Join-Path $agentRoot 'agent/execution.py')){
        $answer=Invoke-M2aNative $python @('-B','-m','agent.execution','disable') $agentRoot
        if($answer.exitCode){throw 'Local command switch is busy; leave cloud paused and reconcile first.'}
    }
    if($operation.sourceBackup){
        $sourceBackup=[IO.Path]::GetFullPath([string]$operation.sourceBackup)
        if(-not $sourceBackup.StartsWith($backupRoot+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Owned source backup required.'}
        $answer=Invoke-M2aNative 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $sourceBackup 'agent-source-update.ps1'),'-Action','Rollback','-BackupPath',$sourceBackup) $sourceBackup
        if($answer.exitCode){throw 'Source rollback refused; cloud remains paused.'}
    }
    $switch=Join-Path $stateRoot 'command-settings.json'
    if($operation.previousSwitchPresent){
        . (Join-Path $directory 'agent-json.ps1')
        $previous=Read-SharedJson -Path (Join-Path $directory 'command-settings.before.json')
        Write-SharedAtomicJson -Path $switch -Value @{schema=1;enabled=[bool]$previous.enabled}
    }elseif(Test-Path -LiteralPath $switch){Remove-Item -LiteralPath $switch}
    Write-Output ('Rollback raw output: '+$script:logPath)
    Write-Output 'Agent source/switch restored. Execution receipts retained; cloud remains paused. No production programs or credentials touched.'
    return
}
if($ExpectedCommit -notmatch '^[a-f0-9]{40}$' -or $ExpectedInstalledCommit -notmatch '^[a-f0-9]{40}$'){throw 'Exact source and installed commits required.'}
foreach($digest in @($ExpectedManifestSHA256,$ExpectedToolsManifestSHA256)){if($digest -notmatch '^[a-fA-F0-9]{64}$'){throw 'Pinned package hashes required.'}}
$SourcePackage=[IO.Path]::GetFullPath($SourcePackage)
$manifestPath=Join-Path $SourcePackage 'deployment-manifest.json'
$toolsRoot=Join-Path $SourcePackage 'update-tool'
$toolsManifestPath=Join-Path $toolsRoot 'tools-manifest.json'
if((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash -ne $ExpectedManifestSHA256 -or (Get-FileHash -LiteralPath $toolsManifestPath -Algorithm SHA256).Hash -ne $ExpectedToolsManifestSHA256){throw 'Pinned package manifest changed.'}
$manifest=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$tools=Get-Content -LiteralPath $toolsManifestPath -Raw | ConvertFrom-Json
if($manifest.commit -ne $ExpectedCommit -or $tools.commit -ne $ExpectedCommit){throw 'Package commit mismatch.'}
$toolNames=@('agent_source_update.py','agent-source-update.ps1','agent-migrate.ps1','agent_legacy_lock.py','agent-acceptance.ps1','agent-json.ps1','agent_state_io.py','agent-m2a-deploy.ps1')
if(@(Compare-Object $toolNames @($tools.sha256.PSObject.Properties.Name)).Count){throw 'Unexpected tool whitelist.'}
foreach($name in $toolNames){if((Get-FileHash -LiteralPath (Join-Path $toolsRoot $name) -Algorithm SHA256).Hash -ne $tools.sha256.$name){throw 'Pinned tool changed.'}}
$installed=Get-Content -LiteralPath (Join-Path $agentRoot 'deployment-manifest.json') -Raw | ConvertFrom-Json
if($installed.commit -ne $ExpectedInstalledCommit){throw 'Installed agent version changed; review it before deployment.'}
. (Join-Path $toolsRoot 'agent-json.ps1')
$switchPath=Join-Path $stateRoot 'command-settings.json'
$previousSwitch=$null
if(Test-Path -LiteralPath $switchPath){
    $previousSwitch=Read-SharedJson -Path $switchPath
    if($previousSwitch.schema -isnot [int] -or $previousSwitch.schema -ne 1 -or $previousSwitch.enabled -isnot [bool] -or @(Compare-Object @('schema','enabled') @($previousSwitch.PSObject.Properties.Name)).Count){throw 'Unexpected nonsecret switch format; preserve and review manually.'}
}
$directory=Join-Path $backupRoot ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)+'-m2a-switch')
[void](New-Item -ItemType Directory -Path $directory)
if($previousSwitch){Write-SharedAtomicJson -Path (Join-Path $directory 'command-settings.before.json') -Value @{schema=1;enabled=[bool]$previousSwitch.enabled}}
Copy-Item -LiteralPath (Join-Path $workspaceRoot 'h4-validation/m0-known-hosts') -Destination (Join-Path $directory 'known-hosts')
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $directory 'agent-m2a-deploy.ps1')
Copy-Item -LiteralPath (Join-Path $toolsRoot 'agent-json.ps1') -Destination (Join-Path $directory 'agent-json.ps1')
$operation=@{schema=1;agentRoot=$agentRoot;before=$ExpectedInstalledCommit;after=$ExpectedCommit;previousSwitchPresent=($null -ne $previousSwitch);sourceBackup=$null}
$operationPath=Join-Path $directory 'm2a-operation.json'
Write-SharedAtomicJson -Path $operationPath -Value $operation
@'
& (Join-Path $PSScriptRoot 'agent-m2a-deploy.ps1') -Action Rollback -OperationFile (Join-Path $PSScriptRoot 'm2a-operation.json')
'@ | Set-Content -LiteralPath (Join-Path $directory 'rollback.ps1') -Encoding utf8
[void][IO.Directory]::CreateDirectory($EvidenceDirectory)
$script:logPath=Join-Path $EvidenceDirectory ('claude-m2a-agent-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')+'.txt')
Write-Output ('M2a switch/source rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "'+(Join-Path $directory 'rollback.ps1')+'"')
Write-Output ('Raw output: '+$script:logPath)
Pause-CloudCommands $directory
$answer=Invoke-M2aNative 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $toolsRoot 'agent-source-update.ps1'),'-SourcePackage',$SourcePackage,'-ExpectedCommit',$ExpectedCommit) $SourcePackage
$match=[regex]::Match($answer.stdout,'(?m)^Backup: (E:\\Backup\\ops-agent-deploy-backups\\[^\r\n]+)\r?$')
if($match.Success){$operation.sourceBackup=$match.Groups[1].Value;Write-SharedAtomicJson -Path $operationPath -Value $operation}
if($answer.exitCode -ne 0 -or -not $operation.sourceBackup){throw 'Agent update did not finish; preserve output and use the recorded rollback. Command switch was not enabled.'}
$answer=Invoke-M2aNative $python @('-B','-m','agent.execution','enable') $agentRoot
if($answer.exitCode){throw 'Source updated but execution switch not enabled; cloud remains paused.'}
$answer=Invoke-M2aNative $python @('-B','-m','agent.execution','status') $agentRoot
if($answer.exitCode){throw 'Execution metadata unavailable; cloud remains paused.'}
Write-Output 'M2a source installed and nonsecret switch enabled; cloud REMAINS PAUSED. Send sanitized receipt for read-only verification and empty-queue activation. No home business POST was requested.'
