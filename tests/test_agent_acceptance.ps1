$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\deploy\agent-acceptance.ps1'),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Acceptance parser error.' }
foreach ($name in @('Assert-OwnedTask','Assert-ExactProcess','Test-RepeatStart')) {
    $node=$ast.Find({param($item) $item -is [Management.Automation.Language.FunctionDefinitionAst] -and $item.Name -eq $name},$true)
    . ([ScriptBlock]::Create($node.Extent.Text))
}
$taskName='OpsConsoleReadonlyAgent';$agentRoot='E:\Backup\ops-agent';$python='C:\fixture\python.exe'
$exe=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$argsText='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+$agentRoot+'\deploy\agent-run.ps1" -AgentRoot "'+$agentRoot+'" -PythonExecutable "'+$python+'"'
$script:fixtureTask=[pscustomobject]@{Description='OPS Console read-only agent; owned task; no production program control.';Actions=@([pscustomobject]@{Execute=$exe;Arguments=$argsText;WorkingDirectory=$agentRoot});Triggers=@([pscustomobject]@{Repetition=[pscustomobject]@{Interval='';Duration=''}},[pscustomobject]@{Repetition=[pscustomobject]@{Interval='PT5M';Duration=''}});Settings=[pscustomobject]@{MultipleInstances=2}}
$script:fixtureProcess=[pscustomobject]@{ExecutablePath=$exe;CommandLine=('"'+$exe+'" '+$argsText)}
$born=[DateTime]::UtcNow;$script:fixtureOwner=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function Get-ScheduledTask {param($TaskName,$TaskPath) if ($TaskName -ne 'OpsConsoleReadonlyAgent' -or $TaskPath -ne '\') { throw 'Foreign task query.' };return $script:fixtureTask}
function Get-CimInstance {param($ClassName,$Filter) if ($Filter -ne 'ProcessId=7777') { throw 'Foreign process query.' };return $script:fixtureProcess}
function Invoke-CimMethod {param($InputObject,$MethodName) if ($MethodName -ne 'GetOwnerSid') { throw 'Foreign CIM method.' };return [pscustomobject]@{ReturnValue=0;Sid=$script:fixtureOwner}}
function Get-Process {param($Id) if ($Id -ne 7777) { throw 'Foreign process query.' };return [pscustomobject]@{StartTime=$born}}
$null=Assert-OwnedTask
Assert-ExactProcess 7777 $born.ToFileTimeUtc() 'supervisor'
function Assert-Refused([ScriptBlock]$Work) { $failed=$false;try { & $Work } catch { $failed=$true };if (-not $failed) { throw 'Unsafe acceptance input allowed.' } }
$script:fixtureProcess.CommandLine+=' --unapproved-flag';Assert-Refused { Assert-ExactProcess 7777 $born.ToFileTimeUtc() 'supervisor' }
$script:fixtureProcess.CommandLine='"'+$exe+'" '+$argsText
Assert-Refused { Assert-ExactProcess 7777 ($born.ToFileTimeUtc()+1) 'supervisor' }
$script:fixtureOwner='S-1-5-18';Assert-Refused { Assert-ExactProcess 7777 $born.ToFileTimeUtc() 'supervisor' }
$script:fixtureOwner=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$script:fixtureTask.Triggers[1].Repetition.Duration='PT1H';Assert-Refused { $null=Assert-OwnedTask }
$script:fixtureTask.Triggers[1].Repetition.Duration=''
$script:fixtureTask.Actions[0].Arguments+=' --unapproved-flag';Assert-Refused { $null=Assert-OwnedTask }
Write-Output 'PASS: exact supervisor accepted; other argv/creation/owner/task action and finite repetition rejected. No actual task/process control.'

if (-not (Test-RepeatStart 1000000000 1030000000) -or (Test-RepeatStart 1000000000 1600000000) -or (Test-RepeatStart 0 1000000000)) { throw 'Repeat timing proof accepted unrelated/invalid start.' }
Write-Output 'PASS: repeat timing proof accepts scheduled start, rejects unrelated/invalid starts.'
