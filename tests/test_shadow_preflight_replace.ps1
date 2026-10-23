#Requires -Version 5.1
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Use Windows PowerShell 5.1 for this fixture.' }
$base=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$fixture=Join-Path $base ('shadow-replace-fixture-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
$marker=Join-Path $fixture 'owned-fixture.txt';'synthetic' | Set-Content -LiteralPath $marker
$helper=Join-Path (Split-Path -Parent $PSScriptRoot) 'deploy\shadow-preflight-replace.ps1'
function FixtureSha([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Dump([string]$Path,$Value) { $Value | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path -Encoding UTF8 }
function Assert($Condition,[string]$Message) { if (-not $Condition) { throw $Message } }
$control=Join-Path $fixture 'control';$sources=Join-Path $fixture 'sources'
New-Item -ItemType Directory -Path $control,$sources | Out-Null
$oldPlan=Join-Path $control 'old-plan.json';Dump $oldPlan @{fixture='old'}
$current=Join-Path $control 'host-settings.json'
Dump $current @{schema=1;enabled=$false;mode='preflight';planPath=$oldPlan;planSha256=(FixtureSha $oldPlan)}
$oldHash=FixtureSha $current
$report=Join-Path $control 'preflight-123.json';$series=Join-Path $control 'preflight-series-123.json'
Dump $report @{fixture='baseline'};Dump $series @{fixture='baseline-series'}
$reportHash=FixtureSha $report;$seriesHash=FixtureSha $series
function Review([string]$Commit) {
    $review=Join-Path $fixture ('review-'+$Commit.Substring(0,1));New-Item -ItemType Directory -Path (Join-Path $review 'code\tools') -Force | Out-Null
    $files=@{}
    foreach ($leaf in @('shadow_dashboard_bootstrap.py','shadow_live_runtime.py','shadow_dashboard_host.py','shadow_sqlite_snapshot.py')) {
        $file=Join-Path $review ('code\tools\'+$leaf);'# inert synthetic fixture' | Set-Content -LiteralPath $file
        $files['tools/'+$leaf]=FixtureSha $file
    }
    $manifest=Join-Path $review 'code\shadow-package.json';Dump $manifest @{schema=1;sourceCommit=$Commit;files=$files}
    $plan=Join-Path $review 'plan.json';Dump $plan @{fixture='new'}
    Dump (Join-Path $review 'host-settings.json') @{schema=1;enabled=$false;mode='preflight';sourceCommit=$Commit;
        packageRoot=(Join-Path $sources $Commit);packageManifestSha256=(FixtureSha $manifest);
        planPath=(Join-Path $control ('plan-'+$Commit+'.json'));planSha256=(FixtureSha $plan)}
    return $review
}
try {
    $commit=('b'*40);$review=Review $commit;$backup=Join-Path $fixture 'backup'
    $rejected=$false
    try { & $helper -ReviewRoot $review -ControlRoot $control -SourceParent $sources -BackupRoot $backup } catch { $rejected=$true }
    Assert $rejected 'Explicit apply gate failed.';Assert (-not (Test-Path -LiteralPath $backup)) 'Gate wrote backup.'
    & $helper -ReviewRoot $review -ControlRoot $control -SourceParent $sources -BackupRoot $backup -Apply
    Assert ((FixtureSha (Join-Path $backup 'host-settings.before.json')) -eq $oldHash) 'Old settings backup differs.'
    Assert ((FixtureSha $current) -eq (FixtureSha (Join-Path $review 'host-settings.json'))) 'Settings replacement differs.'
    Assert ((FixtureSha $report) -eq $reportHash -and (FixtureSha $series) -eq $seriesHash) 'Baseline report changed.'
    Assert ((FixtureSha $oldPlan) -eq (FixtureSha (Join-Path $backup 'plan.before.json'))) 'Old plan not retained.'
    Assert (@(Get-ChildItem -LiteralPath $control -Filter '.settings-before-*.json').Count -eq 1) 'Atomic replacement backup absent.'
    $incomingHash=FixtureSha $current;$bad=Review ('c'*40);'tampered' | Add-Content -LiteralPath (Join-Path $bad 'plan.json')
    $badBackup=Join-Path $fixture 'bad-backup';$rejected=$false
    try { & $helper -ReviewRoot $bad -ControlRoot $control -SourceParent $sources -BackupRoot $badBackup -Apply } catch { $rejected=$true }
    Assert $rejected 'Tampered plan was accepted.';Assert ((FixtureSha $current) -eq $incomingHash) 'Failed update changed settings.'
    Assert (-not (Test-Path -LiteralPath $badBackup)) 'Invalid update wrote runtime backup.'
    $bad=Review ('d'*40);$value=Get-Content -LiteralPath (Join-Path $bad 'host-settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $value.enabled=$true;$value.mode='observe';Dump (Join-Path $bad 'host-settings.json') $value;$rejected=$false
    try { & $helper -ReviewRoot $bad -ControlRoot $control -SourceParent $sources -BackupRoot $badBackup -Apply } catch { $rejected=$true }
    Assert $rejected 'Observe activation accepted.';Assert ((FixtureSha $current) -eq $incomingHash) 'Observe rejection changed settings.'
    $ast=[Management.Automation.Language.Parser]::ParseFile($helper,[ref]$null,[ref]$null)
    $forbidden=$ast.FindAll({param($node) $node -is [Management.Automation.Language.CommandAst] -and $node.GetCommandName() -in @('Stop-Process','Start-Process','Invoke-WebRequest','Invoke-RestMethod','Restart-Service')},$true)
    Assert ($forbidden.Count -eq 0) 'Placement helper contains process/network commands.'
    Write-Host 'PASS: PS5.1 replacement; prior settings backed up; baseline reports unchanged; invalid/observe updates refused; no restart/request.'
} finally {
    $resolved=[IO.Path]::GetFullPath($fixture)
    if (-not $resolved.StartsWith($base+'\',[StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path -LiteralPath $marker)) { throw 'Unsafe fixture cleanup path.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
exit 0
