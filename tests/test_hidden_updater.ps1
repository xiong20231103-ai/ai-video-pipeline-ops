$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\deploy\agent-source-update.ps1'),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'Updater syntax error.'}
$function=$ast.Find({param($node)$node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-AgentTool'},$true)
if(-not $function){throw 'Hidden helper function missing.'}
Invoke-Expression $function.Extent.Text
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('ops-hidden-helper-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture|Out-Null
try{
    $python=if($env:OPS_AGENT_TEST_PYTHON){$env:OPS_AGENT_TEST_PYTHON}else{(Get-Command python).Source}
    $helper=Join-Path $fixture 'fixture with spaces.py'
    @'
import ctypes,json,sys
if '--fail' in sys.argv:raise SystemExit(7)
print(json.dumps({'consoleWindow':ctypes.windll.kernel32.GetConsoleWindow(),'arguments':sys.argv[1:]}))
'@ | Set-Content -Encoding utf8 -LiteralPath $helper
    $result=Invoke-AgentTool 'argument with spaces' '--fixture-only'
    if($LASTEXITCODE -ne 0){throw 'Hidden fixture helper failed.'}
    $state=$result|ConvertFrom-Json
    if($state.consoleWindow -ne 0){throw 'Native helper had a console window.'}
    if($state.arguments.Count -ne 2 -or $state.arguments[0] -ne 'argument with spaces'){throw 'Argument boundaries lost.'}
    $null=Invoke-AgentTool '--fail'
    if($LASTEXITCODE -ne 7){throw 'Native exit code was lost.'}
    $script:LASTEXITCODE=0;$global:LASTEXITCODE=0
    Write-Output 'PASS: real Python helper has no console window; spaced arguments preserved; no production access.'
}finally{
    # Only the two explicitly named fixture paths created above are removed.
    Remove-Item -LiteralPath $helper -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $fixture
}
