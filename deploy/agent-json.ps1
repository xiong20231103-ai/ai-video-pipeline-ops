# Shared state readers permit replacement; retries never print JSON payloads.
function Read-SharedJson {
    param([Parameter(Mandatory=$true)][string]$Path)
    $lastType='Unknown'
    for ($attempt=0;$attempt -lt 10;$attempt++) {
        $stream=$null;$reader=$null
        try {
            $share=[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
            $stream=New-Object IO.FileStream($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,$share)
            $reader=New-Object IO.StreamReader($stream,(New-Object Text.UTF8Encoding($false,$true)),$true)
            $text=$reader.ReadToEnd()
            $value=ConvertFrom-Json -InputObject $text -ErrorAction Stop
            if ([string]::IsNullOrWhiteSpace($text)) { throw 'Empty state JSON.' }
            return $value
        } catch { $lastType=$_.Exception.GetType().Name }
        finally { if ($reader) {$reader.Dispose()} elseif ($stream) {$stream.Dispose()} }
        if ($attempt -lt 9) { Start-Sleep -Milliseconds 200 }
    }
    throw (New-Object IO.InvalidDataException("State JSON unavailable after 10 read attempts ($lastType)."))
}
function Write-SharedAtomicJson {
    param([Parameter(Mandatory=$true)][string]$Path,[Parameter(Mandatory=$true)]$Value)
    $temporary=$Path+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
    $stream=$null
    try {
        $bytes=(New-Object Text.UTF8Encoding($false)).GetBytes(($Value | ConvertTo-Json -Compress -Depth 20))
        $share=[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
        $stream=New-Object IO.FileStream($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,$share)
        $stream.Write($bytes,0,$bytes.Length);$stream.Flush($true);$stream.Dispose();$stream=$null
        for ($attempt=0;$attempt -lt 10;$attempt++) {
            try {
                if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary,$Path,[NullString]::Value) } else { [IO.File]::Move($temporary,$Path) }
                return
            } catch [IO.IOException] { if ($attempt -eq 9) {throw} }
              catch [UnauthorizedAccessException] { if ($attempt -eq 9) {throw} }
            Start-Sleep -Milliseconds 200
        }
    } finally {
        if ($stream) {$stream.Dispose()}
        if ([IO.File]::Exists($temporary)) {[IO.File]::Delete($temporary)}
    }
}
