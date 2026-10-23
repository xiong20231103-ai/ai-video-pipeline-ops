# SHA256 uses the framework API, available in Windows PowerShell 5.1 without
# depending on module auto-discovery inherited from a pwsh 7 parent.
function Get-ShadowSha256([string]$Path) {
    $hash=[Security.Cryptography.SHA256]::Create()
    $stream=[IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose();$hash.Dispose() }
}
# Explicit launcher branch only. Dot-sourcing does not start anything.
function Invoke-ShadowOrLegacy {
    param(
        [Parameter(Mandatory=$true)][string]$Python,
        [Parameter(Mandatory=$true)][string]$Project,
        [Parameter(Mandatory=$true)][string]$SettingsPath,
        [scriptblock]$ShadowAttempt = {
            param($PythonPath,$ProjectPath,$SettingsFile,$Bootstrap)
            # Windows PowerShell 5.1 can turn redirected native stderr into a
            # terminating NativeCommandError. Do not redirect stderr. Keep any
            # native diagnostic nonterminating and inspect the real exit code.
            $ErrorActionPreference='Continue'
            $global:LASTEXITCODE=1
            & $PythonPath -B $Bootstrap --dashboard-root $ProjectPath --settings $SettingsFile | Out-Host
            return $LASTEXITCODE
        },
        [scriptblock]$LegacyAttempt = {
            param($PythonPath,$ProjectPath)
            & $PythonPath (Join-Path $ProjectPath 'app.py')
        }
    )
    function Write-ShadowLaunchCode([string]$Code) {
        try {
            $folder=Split-Path -Parent $SettingsPath
            $log=Join-Path $folder 'launch-status.log'
            if (-not (Test-Path -LiteralPath $log) -or (Get-Item -LiteralPath $log).Length -lt 65536) {
                ([DateTimeOffset]::UtcNow.ToString('o')+' '+$Code) | Add-Content -LiteralPath $log -Encoding UTF8
            }
        } catch {} # Logging must never stop the original Dashboard.
    }
    $bootstrap=$null
    try {
        if ((Get-Item -LiteralPath $SettingsPath).Length -gt 1048576) { throw 'settings_limit' }
        $settings=Get-Content -LiteralPath $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($settings.enabled -isnot [bool]) { throw 'invalid_switch' }
        if ($settings.enabled -or $settings.mode -eq 'preflight') {
        if ($settings.schema -ne 1 -or $settings.mode -notin @('preflight','observe')) { throw 'invalid_mode' }
        if ($settings.sourceCommit -notmatch '^[a-f0-9]{40}$' -or $settings.packageManifestSha256 -notmatch '^[a-f0-9]{64}$') { throw 'reviewed_package_required' }
        $package=[IO.Path]::GetFullPath([string]$settings.packageRoot)
        $parts=@(Get-Item -Force -LiteralPath $package)
        $parent=Split-Path -Parent $package
        while ($parent) { $parts+=Get-Item -Force -LiteralPath $parent; $next=Split-Path -Parent $parent; if($next -eq $parent){break};$parent=$next }
        if ($parts | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'linked_package' }
        $manifestPath=Join-Path $package 'shadow-package.json'
        if ((Get-ShadowSha256 $manifestPath) -ne $settings.packageManifestSha256) { throw 'package_manifest_mismatch' }
        $manifest=Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.sourceCommit -ne $settings.sourceCommit) { throw 'package_commit_mismatch' }
        $bootstrap=Join-Path $package 'tools\shadow_dashboard_bootstrap.py'
        $expected=$manifest.files.'tools/shadow_dashboard_bootstrap.py'
        if (-not $expected -or (Get-ShadowSha256 $bootstrap) -ne $expected) { throw 'bootstrap_mismatch' }
        }
    } catch {
        Write-ShadowLaunchCode 'shadow_setup_rejected_using_legacy'
        $bootstrap=$null # Validation failed before any optional process starts.
    }
    if ($null -ne $bootstrap) {
        # This call is deliberately OUTSIDE the preparation fallback catch.
        # A running service's crash/kill/bind error must propagate to watchdog.
        try { $code=& $ShadowAttempt $Python $Project $SettingsPath $bootstrap }
        catch { Write-ShadowLaunchCode 'shadow_invoke_failed_no_fallback';$global:LASTEXITCODE=1;return }
        if ($code -isnot [int]) { $global:LASTEXITCODE=1;return }
        if ($code -ne 75) { $global:LASTEXITCODE=$code;return }
        Write-ShadowLaunchCode 'shadow_prepare_failed_using_legacy'
    }
    # Fresh, unchanged app.py process; no shadow imports or bindings remain.
    & $LegacyAttempt $Python $Project
}
