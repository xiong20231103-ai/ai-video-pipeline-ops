$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$path=Join-Path $PSScriptRoot '../deploy/agent-m2a-deploy.ps1'
$ast=[Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'M2a deployment syntax failed.'}
$native=$ast.Find({param($node)$node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-M2aNative'},$true)
$pause=$ast.Find({param($node)$node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Pause-CloudCommands'},$true)
if(-not $native -or -not $pause){throw 'Deployment protocol functions missing.'}
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('ops-m2a-deploy-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($fixture)
try {
    $script:logPath=Join-Path $fixture 'native-output.txt'
    $python=if($env:OPS_AGENT_TEST_PYTHON){$env:OPS_AGENT_TEST_PYTHON}else{(Get-Command python).Source}
    $probe=Join-Path $fixture 'console fixture.py'
    @'
import ctypes,json,sys
print(json.dumps({"consoleHandle":int(ctypes.windll.kernel32.GetConsoleWindow()),"arguments":sys.argv[1:]}))
'@ | Set-Content -LiteralPath $probe -Encoding utf8
    Invoke-Expression $native.Extent.Text
    $answer=Invoke-M2aNative $python @('-B',$probe,'fixture spaced argument') $fixture
    $result=$answer.stdout|ConvertFrom-Json
    if($answer.exitCode -or $result.consoleHandle -ne 0 -or $result.arguments[0] -ne 'fixture spaced argument'){throw 'Native helper exposed a window or changed arguments.'}
    $refused=$false
    try{Invoke-M2aNative $python @('unsupported"argument') $fixture|Out-Null}catch{$refused=$true}
    if(-not $refused){throw 'Unsafe quoting was accepted.'}
    # Replace the transport before invoking the pause protocol: zero SSH calls.
    function Invoke-M2aNative {
        param([string]$Executable,[string[]]$Items,[string]$WorkingDirectory)
        $script:capturedItems=$Items;$script:capturedDirectory=$WorkingDirectory
        return [pscustomobject]@{exitCode=$script:fixtureExit;stdout='fixture';stderr=''}
    }
    $keyPath='C:\fixture\not-a-real-key';$script:fixtureExit=0
    Invoke-Expression $pause.Extent.Text
    Pause-CloudCommands $fixture
    if($script:capturedDirectory -ne $fixture -or $script:capturedItems -notcontains 'StrictHostKeyChecking=yes' -or $script:capturedItems -notcontains 'UserKnownHostsFile=known-hosts' -or $script:capturedItems[-1] -notlike '*pause --wait 60*'){throw 'Pinned cloud pause contract changed.'}
    Pause-CloudCommands $fixture -CancelQueued
    if($script:capturedItems[-1] -notlike '*--cancel-queued*'){throw 'Rollback did not request pre-send cancellation.'}
    $script:fixtureExit=2;$refused=$false
    try{Pause-CloudCommands $fixture}catch{$refused=$true}
    if(-not $refused){throw 'Cloud drain failure was ignored.'}
    Write-Output 'PASS: actual child has no console; argument bounds preserved; pinned SSH pause/rollback protocol refuses failed drain; no production/task/SSH operation.'
} finally {
    $resolved=[IO.Path]::GetFullPath($fixture)
    if(-not $resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()),[StringComparison]::OrdinalIgnoreCase) -or [IO.Path]::GetFileName($resolved) -notmatch '^ops-m2a-deploy-[a-fA-F0-9]{32}$'){throw 'Fixture path escaped owned temp directory.'}
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
