#Requires -Version 5.1
# Reviewable placement only: no service/process control, requests or activation.
param(
    [Parameter(Mandatory=$true)][string]$ReviewRoot,
    [Parameter(Mandatory=$true)][string]$ControlRoot,
    [Parameter(Mandatory=$true)][string]$SourceParent,
    [Parameter(Mandatory=$true)][string]$BackupRoot,
    [switch]$Apply
)
$ErrorActionPreference='Stop'
if (-not $Apply) { throw 'Review required. No placement without explicit Apply.' }
function PlainPath([string]$Value) {
    if (-not [IO.Path]::IsPathRooted($Value)) { throw 'Absolute path required.' }
    $resolved=[IO.Path]::GetFullPath($Value).TrimEnd('\')
    if ($resolved -eq [IO.Path]::GetPathRoot($resolved).TrimEnd('\')) { throw 'Drive root is not a permitted placement directory.' }
    $cursor=$resolved
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -Force -LiteralPath $cursor).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked path rejected.' }
        }
        $next=Split-Path -Parent $cursor
        if ($next -eq $cursor) { break };$cursor=$next
    }
    return $resolved
}
function Sha([string]$Path) { return (Get-FileHash -LiteralPath (PlainPath $Path) -Algorithm SHA256).Hash.ToLowerInvariant() }
function CheckSha([string]$Path,[string]$Expected) {
    if ($Expected -notmatch '^[0-9a-f]{64}$' -or (Sha $Path) -ne $Expected) { throw 'Artifact hash mismatch.' }
}
function Json([string]$Path) {
    $Path=PlainPath $Path
    if ((Get-Item -LiteralPath $Path).Length -gt 2097152) { throw 'JSON size limit.' }
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}
function Separate([string]$A,[string]$B) {
    if ($A -eq $B -or $A.StartsWith($B+'\',[StringComparison]::OrdinalIgnoreCase) -or $B.StartsWith($A+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Overlapping review/backup/source/control paths.' }
}
$ReviewRoot=PlainPath $ReviewRoot;$ControlRoot=PlainPath $ControlRoot
$SourceParent=PlainPath $SourceParent;$BackupRoot=PlainPath $BackupRoot
Separate $BackupRoot $ControlRoot;Separate $BackupRoot $SourceParent;Separate $BackupRoot $ReviewRoot
Separate $ControlRoot $SourceParent;Separate $ControlRoot $ReviewRoot;Separate $SourceParent $ReviewRoot
$incoming=Join-Path $ReviewRoot 'host-settings.json';$settings=Json $incoming
$required=@('schema','mode','enabled','sourceCommit','packageRoot','packageManifestSha256','planPath','planSha256')
if (Compare-Object ($required | Sort-Object) ($settings.PSObject.Properties.Name | Sort-Object)) { throw 'Settings keys invalid.' }
if ($settings.schema -ne 1 -or $settings.enabled -isnot [bool] -or $settings.enabled -ne $false -or $settings.mode -ne 'preflight' -or $settings.sourceCommit -notmatch '^[a-f0-9]{40}$') { throw 'Disabled preflight only.' }
$source=PlainPath ([string]$settings.packageRoot);$targetPlan=PlainPath ([string]$settings.planPath)
if ((Split-Path -Parent $source) -ne $SourceParent -or (Split-Path -Leaf $source) -ne $settings.sourceCommit) { throw 'Source must be a fresh commit directory under the explicit source parent.' }
if ((Split-Path -Parent $targetPlan) -ne $ControlRoot) { throw 'Plan must be under the explicit control directory.' }
$current=Join-Path $ControlRoot 'host-settings.json';$old=Json $current
if ($old.schema -ne 1 -or $old.mode -ne 'preflight' -or $old.enabled -isnot [bool] -or $old.enabled -ne $false) { throw 'Existing mode is not disabled preflight; review again.' }
$oldPlan=PlainPath ([string]$old.planPath)
if ((Split-Path -Parent $oldPlan) -ne $ControlRoot -or [IO.Path]::GetExtension($oldPlan) -ne '.json') { throw 'Old plan must be a JSON file inside the control directory.' }
CheckSha $oldPlan $old.planSha256
if ($oldPlan -eq $targetPlan -or (Test-Path -LiteralPath $targetPlan) -or (Test-Path -LiteralPath $source) -or (Test-Path -LiteralPath $BackupRoot)) { throw 'Never overwrite an old plan, source package or backup.' }
$code=PlainPath (Join-Path $ReviewRoot 'code');$manifestFile=Join-Path $code 'shadow-package.json'
CheckSha $manifestFile $settings.packageManifestSha256
CheckSha (Join-Path $ReviewRoot 'plan.json') $settings.planSha256
$manifest=Json $manifestFile
if ($manifest.schema -ne 1 -or $manifest.sourceCommit -ne $settings.sourceCommit) { throw 'Manifest commit mismatch.' }
$files=@($manifest.files.PSObject.Properties)
if ($files.Count -lt 1 -or $files.Count -gt 512) { throw 'Manifest file count invalid.' }
foreach ($requiredFile in @('tools/shadow_dashboard_bootstrap.py','tools/shadow_live_runtime.py','tools/shadow_dashboard_host.py','tools/shadow_sqlite_snapshot.py')) {
    if ($files.Name -notcontains $requiredFile) { throw 'Bootstrap dependency missing.' }
}
$total=0
foreach ($entry in $files) {
    if ($entry.Name -match '(^/|\\|:|(^|/)\.\.(/|$))') { throw 'Unsafe manifest path.' }
    $path=Join-Path $code $entry.Name
    $length=(Get-Item -LiteralPath (PlainPath $path)).Length;$total+=$length
    if ($length -gt 2097152 -or $total -gt 33554432) { throw 'Source package size limit.' }
    CheckSha $path $entry.Value
}
$actual=@(Get-ChildItem -LiteralPath $code -File -Recurse -Force | ForEach-Object { PlainPath $_.FullName | Out-Null; $_.FullName.Substring($code.Length+1).Replace('\','/') })
if (Compare-Object ((@('shadow-package.json')+@($files.Name)) | Sort-Object) ($actual | Sort-Object)) { throw 'Unlisted code file.' }
$oldHash=Sha $current;$incomingHash=Sha $incoming
# Backup the prior settings/plan before any runtime placement. Reports stay put.
New-Item -ItemType Directory -Path $BackupRoot | Out-Null
Copy-Item -LiteralPath $current -Destination (Join-Path $BackupRoot 'host-settings.before.json')
CheckSha (Join-Path $BackupRoot 'host-settings.before.json') $oldHash
if (Test-Path -LiteralPath $oldPlan) {
    $oldPlanHash=Sha $oldPlan
    Copy-Item -LiteralPath $oldPlan -Destination (Join-Path $BackupRoot 'plan.before.json')
    CheckSha (Join-Path $BackupRoot 'plan.before.json') $oldPlanHash
}
$baseline=@(Get-ChildItem -LiteralPath $ControlRoot -File | Where-Object { $_.Name -match '^preflight-(?:series-)?[0-9]+\.json$' } | ForEach-Object {
    [pscustomobject]@{name=$_.Name;sha256=(Sha $_.FullName);bytes=$_.Length}
})
$baseline | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $BackupRoot 'baseline-report-hashes.json') -Encoding UTF8
New-Item -ItemType Directory -Path $source -Force | Out-Null
foreach ($entry in $files) {
    $target=Join-Path $source $entry.Name
    New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $code $entry.Name) -Destination $target
    CheckSha $target $entry.Value
}
Copy-Item -LiteralPath $manifestFile -Destination (Join-Path $source 'shadow-package.json')
CheckSha (Join-Path $source 'shadow-package.json') $settings.packageManifestSha256
Copy-Item -LiteralPath (Join-Path $ReviewRoot 'plan.json') -Destination $targetPlan
CheckSha $targetPlan $settings.planSha256
CheckSha $current $oldHash # Refuse concurrent settings edits before replacement.
$stamp=[Guid]::NewGuid().ToString('N')
$temporary=Join-Path $ControlRoot ('.settings-new-'+$stamp+'.json')
$atomicBackup=Join-Path $ControlRoot ('.settings-before-'+$stamp+'.json')
Copy-Item -LiteralPath $incoming -Destination $temporary
CheckSha $temporary $incomingHash
# All arguments absolute; a real backup path avoids the PS5.1 null-path issue.
[IO.File]::Replace($temporary,$current,$atomicBackup)
CheckSha $current $incomingHash;CheckSha $atomicBackup $oldHash
foreach ($row in $baseline) { CheckSha (Join-Path $ControlRoot $row.name) $row.sha256 }
Write-Host ('Prior settings backup: '+(Join-Path $BackupRoot 'host-settings.before.json'))
Write-Host ('Baseline reports retained: '+$baseline.Count)
Write-Host 'Disabled preflight replaced. No restart, request, cleanup, retry or observe activation was performed.'
