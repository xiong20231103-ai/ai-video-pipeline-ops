[CmdletBinding()]
param([string]$ResultPath)
$ErrorActionPreference='Stop'
$project=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('pip-dashboard-tests-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($fixture)
$results=[Collections.Generic.List[object]]::new()
try {
 foreach($entry in @('launch.ps1','dashboard-watchdog.ps1')) {
  foreach($scenario in @('child','transient','failure')) {
   $case=Join-Path $fixture ($entry+'-'+$scenario)
   [void][IO.Directory]::CreateDirectory((Join-Path $case 'deploy\pip'))
   Copy-Item -LiteralPath (Join-Path $project $entry) -Destination (Join-Path $case $entry)
   $native=switch($scenario){
    'child' { 'function Get-PipNativeConsoleIdentity {[pscustomobject]@{ProcessSessionId=2;ConsoleSessionId=1}}' }
    'transient' { 'function Get-PipNativeConsoleIdentity {[pscustomobject]@{ProcessSessionId=1;ConsoleSessionId=4294967295}}' }
    'failure' { "function Get-PipNativeConsoleIdentity {throw 'sensitive-marker-must-not-appear'}" }
   }
   $guard=(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'SessionGuard.ps1') -Raw)+"`n"+$native
   Set-Content -LiteralPath (Join-Path $case 'deploy\pip\SessionGuard.ps1') -Value $guard -Encoding UTF8
   $runner=Join-Path $case 'test-runner.ps1'
   # Child-only environment; no production config, dependency installation or
   # application exists in the fixture. A missed early guard fails the test.
   $quoted=$case.Replace("'","''")
   Set-Content -LiteralPath $runner -Encoding UTF8 -Value "`$env:LOCALAPPDATA='$quoted'; `$env:SESSIONNAME='Console'; & '$quoted\$entry'"
   $arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$runner+'"'
   $process=Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WindowStyle Hidden -PassThru
   try {
    if(-not $process.WaitForExit(10000)){ $process.Kill();throw 'Own test child timed out' }
    $process.Refresh()
    if($process.ExitCode -ne 0){throw ('Entry did not refuse cleanly: '+$entry+' '+$scenario)}
   } finally { $process.Dispose() }
   $files=@(Get-ChildItem -LiteralPath (Join-Path $case 'data\session-guard') -Filter '*.json')
   if($files.Count -ne 1){throw 'Expected exactly one diagnostic record'}
   $json=Get-Content -LiteralPath $files[0].FullName -Raw
   $record=$json | ConvertFrom-Json
   $expected=switch($scenario){'child' {'not-console-session'} 'transient' {'console-session-transient'} 'failure' {'session-query-failed'}}
   if($record.reason -ne $expected -or $json -match 'sensitive-marker' -or (Test-Path -LiteralPath (Join-Path $case 'data\dashboard_watchdog_status.json'))){throw 'Unexpected side effect or diagnostic'}
   $results.Add([pscustomobject]@{entry=$entry;scenario=$scenario;pass=$true})
  }
 }
 if($ResultPath){$results | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding UTF8}
 [pscustomobject]@{cases=$results.Count;passed=$results.Count;productionApplicationsStarted=0;method='Full entry scripts in temporary fixtures with mocked native identity, including spoofed SESSIONNAME'} | ConvertTo-Json
} finally {
 # Keep fixtures as evidence; this test performs no recursive deletion.
 Write-Output ('Test fixtures: '+$fixture)
}
