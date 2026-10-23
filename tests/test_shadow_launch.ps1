$ErrorActionPreference='Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'deploy\shadow-launch.ps1')
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('shadow-launch-'+[Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($fixture) | Out-Null
try {
    $settings=Join-Path $fixture 'settings.json'
    $script:legacyCalls=0;$script:shadowCalls=0
    $legacy={param($PythonPath,$ProjectPath) $script:legacyCalls++;$global:LASTEXITCODE=0}
    $shadow={param($PythonPath,$ProjectPath,$SettingsFile,$Bootstrap) $script:shadowCalls++;return 75}
    # Disabled means exactly the original entry, no package lookup/attempt.
    @{schema=1;enabled=$false;mode='observe'} | ConvertTo-Json | Set-Content -LiteralPath $settings -Encoding UTF8
    Invoke-ShadowOrLegacy -Python 'fixture-python' -Project $fixture -SettingsPath $settings -ShadowAttempt $shadow -LegacyAttempt $legacy
    if($script:legacyCalls -ne 1 -or $script:shadowCalls -ne 0){throw 'disabled branch changed'}
    # Enabled but missing/corrupt optional package falls back exactly once.
    @{schema=1;enabled=$true;mode='observe';sourceCommit=('a'*40);packageRoot=(Join-Path $fixture 'missing');packageManifestSha256=('b'*64)} | ConvertTo-Json | Set-Content -LiteralPath $settings -Encoding UTF8
    Invoke-ShadowOrLegacy -Python 'fixture-python' -Project $fixture -SettingsPath $settings -ShadowAttempt $shadow -LegacyAttempt $legacy
    if($script:legacyCalls -ne 2 -or $script:shadowCalls -ne 0){throw 'broken package did not fall back once'}
    $log=Get-Content -LiteralPath (Join-Path $fixture 'launch-status.log') -Raw
    if($log -notmatch 'shadow_setup_rejected_using_legacy' -or $log -match 'Exception|missing'){throw 'diagnostic is not fixed-code'}
    # Syntactically corrupt switch also falls back without printing its body.
    '{"enabled": true, "private-canary":' | Set-Content -LiteralPath $settings -Encoding UTF8
    Invoke-ShadowOrLegacy -Python 'fixture-python' -Project $fixture -SettingsPath $settings -ShadowAttempt $shadow -LegacyAttempt $legacy
    if($script:legacyCalls -ne 3){throw 'invalid settings did not fall back'}
    # Only the explicit preparation failure code authorizes fallback.
    $package=Join-Path $fixture 'package'
    [IO.Directory]::CreateDirectory((Join-Path $package 'tools')) | Out-Null
    $bootstrap=Join-Path $package 'tools\shadow_dashboard_bootstrap.py'
    '# inert fixture' | Set-Content -LiteralPath $bootstrap -Encoding UTF8
    $manifestPath=Join-Path $package 'shadow-package.json'
    @{sourceCommit=('a'*40);files=@{'tools/shadow_dashboard_bootstrap.py'=(Get-ShadowSha256 $bootstrap)}} | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    @{schema=1;enabled=$true;mode='observe';sourceCommit=('a'*40);packageRoot=$package;packageManifestSha256=(Get-ShadowSha256 $manifestPath)} | ConvertTo-Json | Set-Content -LiteralPath $settings -Encoding UTF8
    Invoke-ShadowOrLegacy -Python 'fixture-python' -Project $fixture -SettingsPath $settings -ShadowAttempt $shadow -LegacyAttempt $legacy
    if($script:legacyCalls -ne 4 -or $script:shadowCalls -ne 1){throw 'optional process failure did not fall back once'}
    $success={param($PythonPath,$ProjectPath,$SettingsFile,$Bootstrap) $script:shadowCalls++;return 0}
    Invoke-ShadowOrLegacy -Python 'fixture-python' -Project $fixture -SettingsPath $settings -ShadowAttempt $success -LegacyAttempt $legacy
    if($script:legacyCalls -ne 4 -or $script:shadowCalls -ne 2){throw 'successful optional process started duplicate legacy'}
    foreach($exitCode in @(1,23,-1)) {
        $script:fixtureExit=$exitCode
        $failed={param($PythonPath,$ProjectPath,$SettingsFile,$Bootstrap) $script:shadowCalls++;return $script:fixtureExit}
        Invoke-ShadowOrLegacy -Python 'fixture-python' -Project $fixture -SettingsPath $settings -ShadowAttempt $failed -LegacyAttempt $legacy
        if($script:legacyCalls -ne 4 -or $LASTEXITCODE -ne $exitCode){throw 'service failure incorrectly restarted legacy'}
    }
    Write-Output 'Shadow launcher fallback fixtures passed; no real process or service started.'
    # GitHub's PowerShell wrapper exits with LASTEXITCODE. The negative-code
    # cases above are assertions, not this test script's final failure status.
    $global:LASTEXITCODE=0
} finally {
    # Only this fresh synthetic fixture directory is removed.
    $full=[IO.Path]::GetFullPath($fixture)
    $base=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')+'\'
    if(-not $full.StartsWith($base,[StringComparison]::OrdinalIgnoreCase) -or (Split-Path -Leaf $full) -notmatch '^shadow-launch-[a-f0-9]{32}$'){throw 'fixture cleanup boundary'}
    Remove-Item -LiteralPath $full -Recurse -Force
}
