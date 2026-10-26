# Shared startup-only guard. Dot-sourcing defines functions; it never starts or
# stops a service/application, touches a queue, or changes system settings.
# Do not change the caller's StrictMode when dot-sourced by existing launchers.

function Test-PipConsoleIdentity {
 [CmdletBinding()]
 param([Parameter(Mandatory=$true)][long]$ProcessSessionId,[Parameter(Mandatory=$true)][long]$ConsoleSessionId)
 if($ConsoleSessionId -lt 0 -or $ConsoleSessionId -eq 4294967295){return [pscustomobject]@{Allow=$false;Retry=$true;Reason='console-session-transient'}}
 if($ProcessSessionId -le 0){return [pscustomobject]@{Allow=$false;Retry=$false;Reason='noninteractive-process'}}
 if($ProcessSessionId -ne $ConsoleSessionId){return [pscustomobject]@{Allow=$false;Retry=$false;Reason='not-console-session'}}
 [pscustomobject]@{Allow=$true;Retry=$false;Reason='console-session-matched'}
}

function Get-PipNativeConsoleIdentity {
 if(-not ('PipStartupGuard.NativeSession' -as [type])){
  Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
namespace PipStartupGuard {
 public static class NativeSession {
  [DllImport("kernel32.dll")] public static extern uint WTSGetActiveConsoleSessionId();
  public static int CurrentSessionId() { using (var p = Process.GetCurrentProcess()) return p.SessionId; }
 }
}
'@ -ErrorAction Stop
 }
 [pscustomobject]@{ProcessSessionId=[PipStartupGuard.NativeSession]::CurrentSessionId();ConsoleSessionId=[long][PipStartupGuard.NativeSession]::WTSGetActiveConsoleSessionId()}
}

function Get-PipStartupPermission {
 [CmdletBinding()]
 param([ValidateRange(1,10)][int]$Attempts=5,[ValidateRange(0,1000)][int]$RetryMilliseconds=200)
 for($attempt=1;$attempt -le $Attempts;$attempt++){
  try {
   $identity=Get-PipNativeConsoleIdentity
   $decision=Test-PipConsoleIdentity -ProcessSessionId $identity.ProcessSessionId -ConsoleSessionId $identity.ConsoleSessionId
  } catch {
   # Never include exception text, environment, command arguments or credentials.
   return [pscustomobject]@{Allow=$false;Reason='session-query-failed';Attempts=$attempt;ProcessSessionId=$null;ConsoleSessionId=$null}
  }
  if($decision.Allow -or -not $decision.Retry -or $attempt -eq $Attempts){
   return [pscustomobject]@{Allow=$decision.Allow;Reason=$decision.Reason;Attempts=$attempt;ProcessSessionId=$identity.ProcessSessionId;ConsoleSessionId=$identity.ConsoleSessionId}
  }
  Start-Sleep -Milliseconds $RetryMilliseconds
 }
}

function Write-PipStartupSkip {
 [CmdletBinding()]
 param([Parameter(Mandatory=$true)][string]$LogDirectory,[Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9-]{1,64}$')][string]$Role,[Parameter(Mandatory=$true)]$Decision)
 if($Decision.Allow){return}
 # A distinct record avoids concurrent append corruption and shared .tmp names.
 # Callers must choose a local diagnostics directory, never a production queue.
 try {
  [void][IO.Directory]::CreateDirectory($LogDirectory)
  $record=[ordered]@{schemaVersion=1;at=[DateTimeOffset]::Now.ToString('o');role=$Role;event='startup-skipped';reason=[string]$Decision.Reason;processSessionId=$Decision.ProcessSessionId;consoleSessionId=$Decision.ConsoleSessionId}
  $path=Join-Path $LogDirectory ('startup-skip-'+$Role+'-'+[Guid]::NewGuid().ToString('N')+'.json')
  $record | ConvertTo-Json -Compress | Set-Content -LiteralPath $path -Encoding UTF8 -ErrorAction Stop
 }catch{
  # Logging failure must not change a refusal into permission to launch.
  Write-Warning 'Startup was blocked; diagnostic record could not be written.'
 }
}
