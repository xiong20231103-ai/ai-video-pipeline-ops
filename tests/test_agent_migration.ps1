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
function Invoke-FixturePython { $global:LASTEXITCODE=0;return (@{pid=12345;processCreationFileTime=$born.ToFileTimeUtc()} | ConvertTo-Json -Compress) }
function Get-CimInstance { param($ClassName,$Filter) if ($ClassName -ne 'Win32_Process' -or $Filter -ne 'ProcessId=12345') { throw 'Unexpected process query.' };return $script:fixtureProcess }
function Invoke-CimMethod { param($InputObject,$MethodName) if ($MethodName -ne 'GetOwnerSid') { throw 'Unexpected CIM call.' };return [pscustomobject]@{ReturnValue=0;Sid=$script:fixtureOwner} }
function Get-Process { param($Id) if ($Id -ne 12345) { throw 'Unexpected process query.' };return [pscustomobject]@{StartTime=$script:fixtureTime} }
if (@(Get-VerifiedLegacyOwners).Count -ne 1) { throw 'Expected exact owner accepted.' }
function Assert-Refused { $refused=$false;try { $null=Get-VerifiedLegacyOwners } catch { $refused=$true };if (-not $refused) { throw 'Unexpected holder accepted.' } }
$script:fixtureProcess.CommandLine+=' --other';Assert-Refused
$script:fixtureProcess.CommandLine='"C:\fixture\python.exe" -B -m agent.launcher'
$script:fixtureProcess.ExecutablePath='C:\other\python.exe';Assert-Refused
$script:fixtureProcess.ExecutablePath='C:\fixture\python.exe'
$script:fixtureOwner='S-1-5-18';Assert-Refused;$script:fixtureOwner=$ownerSid
$script:fixtureTime=$born.AddSeconds(1);Assert-Refused
Write-Output 'PASS: exact legacy identity accepted; other argv/interpreter/user/creation rejected; no task registered or process terminated.'
foreach ($name in @('agent-run.ps1','agent-task.ps1','agent-source-update.ps1','agent-migrate.ps1','agent-acceptance.ps1')) {
    [void][Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot ('..\deploy\'+$name)),[ref]$tokens,[ref]$errors)
    if ($errors.Count) { throw ('Parse failure: '+$name) }
}
