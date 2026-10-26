[CmdletBinding()]
param([string]$ResultPath)
$ErrorActionPreference='Stop'
Set-StrictMode -Off
. (Join-Path $PSScriptRoot 'SessionGuard.ps1')
$results=[Collections.Generic.List[object]]::new()
function Assert-Guard([string]$Name,[bool]$Condition){$results.Add([pscustomobject]@{name=$Name;pass=$Condition});if(-not $Condition){throw ('FAIL: '+$Name)}}
$scopeUnchanged=$false
try { $unusedValue=$pipGuardUndefinedFixtureVariable; $scopeUnchanged=$true } catch {}
Assert-Guard 'dot-source preserves caller strict mode' $scopeUnchanged
$d=Test-PipConsoleIdentity 1 1;Assert-Guard 'matching console allowed' $d.Allow
$d=Test-PipConsoleIdentity 2 1;Assert-Guard 'child session refused' (-not $d.Allow -and -not $d.Retry)
$d=Test-PipConsoleIdentity 3 1;Assert-Guard 'other remote session refused' (-not $d.Allow)
$d=Test-PipConsoleIdentity 0 0;Assert-Guard 'service session refused' (-not $d.Allow)
$d=Test-PipConsoleIdentity 1 4294967295;Assert-Guard 'no console retries and refuses' (-not $d.Allow -and $d.Retry)
$d=Test-PipConsoleIdentity 1 -1;Assert-Guard 'signed invalid console retries and refuses' (-not $d.Allow -and $d.Retry)
function Get-PipNativeConsoleIdentity {[pscustomobject]@{ProcessSessionId=2;ConsoleSessionId=1}}
$d=Get-PipStartupPermission -Attempts 2 -RetryMilliseconds 0;Assert-Guard 'mismatch immediately refuses' (-not $d.Allow -and $d.Attempts -eq 1)
$script:queries=0
function Get-PipNativeConsoleIdentity {$script:queries++;[pscustomobject]@{ProcessSessionId=1;ConsoleSessionId=if($script:queries -eq 1){4294967295}else{1}}}
$d=Get-PipStartupPermission -Attempts 2 -RetryMilliseconds 0;Assert-Guard 'transient console recovers within bound' ($d.Allow -and $d.Attempts -eq 2)
function Get-PipNativeConsoleIdentity {[pscustomobject]@{ProcessSessionId=1;ConsoleSessionId=4294967295}}
$d=Get-PipStartupPermission -Attempts 3 -RetryMilliseconds 0;Assert-Guard 'persistent transient ends after bound' (-not $d.Allow -and $d.Attempts -eq 3)
function Get-PipNativeConsoleIdentity {throw 'must-not-leak-this-marker'}
$d=Get-PipStartupPermission -Attempts 2 -RetryMilliseconds 0;Assert-Guard 'query failure closed without exception text' (-not $d.Allow -and $d.Reason -eq 'session-query-failed' -and ($d | ConvertTo-Json) -notmatch 'must-not-leak')
if($ResultPath){$results | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8}
[pscustomobject]@{cases=$results.Count;passed=@($results | Where-Object pass).Count;hostMutations=0;method='Pure decision and mocked native-query tests; no applications launched.'} | ConvertTo-Json
