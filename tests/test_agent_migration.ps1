$ErrorActionPreference='Stop'
# Extract only the pure verification function. Never run migration/task/process control.
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\deploy\agent-migrate.ps1'),[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Migration parse error.' }
$function=$ast.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-VerifiedLegacyOwners'},$true)
. ([ScriptBlock]::Create($function.Extent.Text))
$python='Invoke-FixturePython';$legacy='fixture-only'
$allowedExecutables=@('C:\fixture\python.exe');$launcherPattern='^"C:\\fixture\\python\.exe" -B -m agent\.launcher$'
$ownerSid='S-1-5-21-123-456-789-1000';$born=[DateTime]::UtcNow
$script:fixtureProcess=[pscustomobject]@{CommandLine='"C:\fixture\python.exe" -B -m agent.launcher';ExecutablePath='C:\fixture\python.exe'}
$script:fixtureOwner=$ownerSid;$script:fixtureTime=$born
$script:fixtureHolderCount=1
function Invoke-FixturePython {
    $global:LASTEXITCODE=0
    $items=@(for ($index=0;$index -lt $script:fixtureHolderCount;$index++) { @{pid=(12345+$index);processCreationFileTime=$born.ToFileTimeUtc()} })
    return (ConvertTo-Json -InputObject $items -Compress)
}
function Get-CimInstance { param($ClassName,$Filter) if ($ClassName -ne 'Win32_Process' -or $Filter -notin @('ProcessId=12345','ProcessId=12346')) { throw 'Unexpected process query.' };return $script:fixtureProcess }
function Invoke-CimMethod { param($InputObject,$MethodName) if ($MethodName -ne 'GetOwnerSid') { throw 'Unexpected CIM call.' };return [pscustomobject]@{ReturnValue=0;Sid=$script:fixtureOwner} }
function Get-Process { param($Id) if ($Id -notin @(12345,12346)) { throw 'Unexpected process query.' };return [pscustomobject]@{StartTime=$script:fixtureTime} }
if (@(Get-VerifiedLegacyOwners).Count -ne 1) { throw 'Expected exact owner accepted.' }
$script:fixtureHolderCount=0
if (@(Get-VerifiedLegacyOwners).Count -ne 0) { throw 'Empty owner list must remain empty in Windows PowerShell 5.1.' }
$script:fixtureHolderCount=2
if (@(Get-VerifiedLegacyOwners).Count -ne 2) { throw 'Every lock holder must be verified separately.' }
$script:fixtureHolderCount=1
function Assert-Refused { $refused=$false;try { $null=Get-VerifiedLegacyOwners } catch { $refused=$true };if (-not $refused) { throw 'Unexpected holder accepted.' } }
$script:fixtureProcess.CommandLine+=' --other';Assert-Refused
$script:fixtureProcess.CommandLine='"C:\fixture\python.exe" -B -m agent.launcher'
$script:fixtureProcess.ExecutablePath='C:\other\python.exe';Assert-Refused
$script:fixtureProcess.ExecutablePath='C:\fixture\python.exe'
$script:fixtureOwner='S-1-5-18';Assert-Refused;$script:fixtureOwner=$ownerSid
$script:fixtureTime=$born.AddSeconds(1);Assert-Refused
Write-Output 'PASS: zero/one/multiple holders parsed and verified; exact legacy identity accepted; other argv/interpreter/user/creation rejected; no task registered or process terminated.'
foreach ($name in @('agent-run.ps1','agent-task.ps1','agent-source-update.ps1','agent-migrate.ps1','agent-acceptance.ps1')) {
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot ('..\deploy\'+$name)),[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw ('Parse failure: '+$name) }
}

# Every controller task operation must explicitly target the root task folder.
$updater=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\deploy\agent-source-update.ps1'),[ref]$tokens,[ref]$errors)
$commands=$updater.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst]},$true)
$taskCommands=0
foreach ($command in $commands) {
    if ($command.GetCommandName() -in @('Stop-ScheduledTask','Disable-ScheduledTask')) { throw 'Routine updater must use cooperative stop only.' }
    if ($command.GetCommandName() -notin @('Get-ScheduledTask','Export-ScheduledTask','Start-ScheduledTask')) { continue }
    $taskCommands++
    $elements=$command.CommandElements;$found=$false
    for ($index=0;$index -lt $elements.Count-1;$index++) {
        if ($elements[$index] -is [Management.Automation.Language.CommandParameterAst] -and $elements[$index].ParameterName -eq 'TaskPath') {
            $found=($elements[$index+1] -is [Management.Automation.Language.StringConstantExpressionAst] -and $elements[$index+1].Value -eq '\')
        }
    }
    if (-not $found) { throw 'Routine updater task command must explicitly use root TaskPath.' }
}
if ($taskCommands -lt 3) { throw 'Expected task inspection/start operations missing.' }
Write-Output 'PASS: updater task operations target the explicit root folder; no Stop/Disable task calls.'
