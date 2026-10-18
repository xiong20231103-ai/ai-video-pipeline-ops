$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '..\deploy\agent-json.ps1')
Add-Type -Path (Join-Path $PSScriptRoot '..\deploy\AgentJobRunner.cs')
Add-Type -TypeDefinition @'
using System;using System.IO;using System.Text;using System.Threading;
public static class StateIOFixture {
 public static Thread Hold(string path,int share,int milliseconds) {
  var ready=new ManualResetEventSlim(false);
  var thread=new Thread(()=>{using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,(FileShare)share)){ready.Set();Thread.Sleep(milliseconds);}});
  thread.Start();ready.Wait();return thread;
 }
 public static Thread Repair(string path,string value) {
  var thread=new Thread(()=>{Thread.Sleep(350);File.WriteAllText(path,value,new UTF8Encoding(false));});thread.Start();return thread;
 }
 public static void WriteStatus(string folder,System.Reflection.MethodInfo method) { method.Invoke(null,new object[]{folder,(uint)123,"running",(uint)0,0}); }
 public static string WriterError;
 public static Thread PublishStatus(string folder,System.Reflection.MethodInfo method) {
  WriterError=null;
  var thread=new Thread(()=>{try {for(int i=0;i<80;i++)method.Invoke(null,new object[]{folder,(uint)123,"running",(uint)0,0});} catch(Exception error){WriterError=error.GetType().Name;}});
  thread.Start();return thread;
 }
}
'@
function Assert-IO([bool]$Value,[string]$Reason) { if (-not $Value) {throw $Reason} }
$folder=Join-Path ([IO.Path]::GetTempPath()) ('ops-state-io-'+[Guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($folder)
$path=Join-Path $folder 'state.json'
try {
 Write-SharedAtomicJson -Path $path -Value @{version='old'}
 $share=[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
 $reader=New-Object IO.FileStream($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,$share)
 try {Write-SharedAtomicJson -Path $path -Value @{version='new'}} finally {$reader.Dispose()}
 Assert-IO ((Read-SharedJson $path).version -eq 'new') 'Shared reader blocked replacement.'
 $thread=[StateIOFixture]::Hold($path,0,350)
 $watch=[Diagnostics.Stopwatch]::StartNew()
 try {Assert-IO ((Read-SharedJson $path).version -eq 'new') 'Exclusive handle read did not recover.'} finally {$thread.Join()}
 Assert-IO ($watch.Elapsed.TotalSeconds -ge .2) 'No sharing retry was exercised.'
 [IO.File]::WriteAllText($path,'{')
 $thread=[StateIOFixture]::Repair($path,'{"version":"repaired"}')
 try {Assert-IO ((Read-SharedJson $path).version -eq 'repaired') 'Partial JSON retry did not recover.'} finally {$thread.Join()}
 $thread=[StateIOFixture]::Hold($path,3,350) # Legacy reader denies delete/replace.
 try {Write-SharedAtomicJson $path @{version='after-legacy-reader'}} finally {$thread.Join()}
 Assert-IO ((Read-SharedJson $path).version -eq 'after-legacy-reader') 'Atomic replace did not recover.'
 $legacy=New-Object IO.FileStream($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite)
 $failed=$false
 try {try {Write-SharedAtomicJson $path @{version='must-not-publish'}} catch {$failed=$true}} finally {$legacy.Dispose()}
 Assert-IO $failed 'Persistent write conflict must fail boundedly.'
 Assert-IO ((Read-SharedJson $path).version -eq 'after-legacy-reader') 'Failed writer damaged old state.'
 Assert-IO (@(Get-ChildItem -LiteralPath $folder -Filter '*.tmp').Count -eq 0) 'Failed writer leaked temporary file.'
 $status=Join-Path $folder 'task-job.json'
 Write-SharedAtomicJson $status @{schema=2;phase='running'}
 $method=[OpsAgentJob].GetMethod('Status',[Reflection.BindingFlags]'NonPublic,Static')
 $thread=[StateIOFixture]::Hold($status,3,350)
 try {[StateIOFixture]::WriteStatus($folder,$method)} finally {$thread.Join()}
 Assert-IO ((Read-SharedJson $status).launcherPid -eq 123) 'C# atomic status retry did not recover.'
 $thread=[StateIOFixture]::PublishStatus($folder,$method)
 try {for ($i=0;$i -lt 80;$i++) {Assert-IO ((Read-SharedJson $status).phase -eq 'running') 'Concurrent status parse failed.'}} finally {$thread.Join()}
 Assert-IO ([string]::IsNullOrEmpty([StateIOFixture]::WriterError)) 'Concurrent C# writer failed.'
 [IO.File]::WriteAllText($path,'{not-json-fixture-payload')
 $script:sleeps=0
 function Start-Sleep {param($Milliseconds) $script:sleeps++}
 $failed=$false
 try {Read-SharedJson $path | Out-Null} catch {$failed=$true;Assert-IO ($_.Exception.Message -notlike '*fixture-payload*') 'Error leaked JSON payload.'}
 Remove-Item Function:Start-Sleep
 Assert-IO ($failed -and $script:sleeps -eq 9) 'Reader must exhaust 10 attempts, without fake success.'
 Write-Output 'PASS: real exclusive/share-delete conflicts, partial JSON, atomic replacement/retry, persistent-failure preservation, concurrent C# writer/PowerShell readers, bounded parse failure; temp files only.'
} finally {
 # Enumerate/delete only direct files under this exact newly-created test directory.
 if ((Split-Path $folder -Parent) -ne ([IO.Path]::GetTempPath()).TrimEnd('\')) {throw 'Fixture cleanup path mismatch.'}
 foreach ($file in [IO.Directory]::GetFiles($folder)) {[IO.File]::Delete($file)}
 [IO.Directory]::Delete($folder)
}
