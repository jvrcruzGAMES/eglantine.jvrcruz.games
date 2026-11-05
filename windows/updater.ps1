param([string]$ArgsBase64 = '')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
function Write-UpdateLog([string]$Message) {
    try { Add-Content -LiteralPath (Join-Path $root 'update.log') -Value ("{0:o} {1}" -f [DateTime]::UtcNow, $Message) } catch {}
}
function Read-Current {
    $state = Get-Content -Raw -LiteralPath (Join-Path $root 'current.json') | ConvertFrom-Json
    if ($state.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Invalid local payload identifier' }
    return $state
}
function Expand-SafeArchive([string]$Archive, [string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $base = [IO.Path]::GetFullPath($Destination).TrimEnd([char[]]@('\','/')) + [IO.Path]::DirectorySeparatorChar
        $total = [long]0
        if ($zip.Entries.Count -gt 20000) { throw 'Archive contains too many files' }
        foreach ($entry in $zip.Entries) {
            if ([IO.Path]::IsPathRooted($entry.FullName) -or $entry.FullName.Contains(':') -or (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Unsafe archive entry' }
            foreach ($segment in ($entry.FullName.TrimEnd([char[]]@('\','/')) -split '[\\/]')) {
                if ($segment -match '[<>:"|?*\x00-\x1F]' -or $segment -match '[. ]$') { throw 'Unsafe Windows filename' }
            }
            $path = [IO.Path]::GetFullPath((Join-Path $Destination $entry.FullName))
            if (-not $path.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) { throw 'Archive path escapes destination' }
            $total += $entry.Length
            if ($total -gt 6GB) { throw 'Archive is too large' }
            if ($entry.FullName.EndsWith('/') -or $entry.FullName.EndsWith('\')) {
                [IO.Directory]::CreateDirectory($path) | Out-Null
            } else {
                [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path)) | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $path, $false)
            }
        }
    } finally { $zip.Dispose() }
}
function Assert-Payload([string]$Archive, $Metadata) {
    if ((Get-Item -LiteralPath $Archive).Length -ne $Metadata.bytes -or (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Metadata.sha256) { throw 'Update checksum or size mismatch' }
}
function Save-Current($State) {
    $temp = Join-Path $root ('current-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    [IO.File]::WriteAllText($temp, ($State | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding($false)))
    $destination = Join-Path $root 'current.json'
    if (Test-Path -LiteralPath $destination) { [IO.File]::Replace($temp, $destination, [NullString]::Value) }
    else { [IO.File]::Move($temp, $destination) }
}
function Get-UpdateUri($Config, $Release) {
    $feed = [Uri]$Config.feed
    if ($feed.Scheme -ne 'https') { throw 'Updates require HTTPS' }
    if ($release.schema -ne 1 -or $release.channel -ne $config.channel -or $release.package -ne $config.package -or $release.platform -ne 'windows') { throw 'Update belongs to a different channel or schema' }
    if ($release.payload.sha256 -notmatch '^[a-f0-9]{64}$' -or $release.payload.bytes -le 0 -or $release.payload.bytes -gt 2GB) { throw 'Invalid update payload metadata' }
    $url = New-Object Uri($feed, [string]$release.payload.url)
    $allowed = $feed.AbsolutePath.Replace('/updates/latest.json', '/releases/')
    if ($url.Scheme -ne 'https' -or $url.Authority -ne $feed.Authority -or -not $url.AbsolutePath.StartsWith($allowed, [StringComparison]::Ordinal)) { throw 'Unexpected update location' }
    return $url
}
$config = Get-Content -Raw -LiteralPath (Join-Path $root 'install.json') | ConvertFrom-Json
$mutex = New-Object Threading.Mutex($false, ('Local\' + $config.package + '-update'))
$locked = $false
$temporary = $null
try {
    try { $locked = $mutex.WaitOne(120000) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Another update is still in progress; launch again shortly' }
    $current = Read-Current
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $feed = [Uri]$config.feed
        if ($feed.Scheme -ne 'https') { throw 'Updates require HTTPS' }
        $release = Invoke-RestMethod -Uri $feed -TimeoutSec 15 -MaximumRedirection 0 -UseBasicParsing
        $url = Get-UpdateUri $config $release
        if ($release.version -ne $current.version -and [DateTimeOffset]::Parse($release.published_at) -ge [DateTimeOffset]::Parse($current.published_at)) {
            if ($release.payload.sha256 -ne $current.sha256) {
                $temporary = Join-Path $root ('.update-' + [Guid]::NewGuid().ToString('N'))
                New-Item -ItemType Directory -Path $temporary | Out-Null
                $archive = Join-Path $temporary 'payload.zip'
                Invoke-WebRequest -Uri $url -OutFile $archive -TimeoutSec 600 -MaximumRedirection 0 -UseBasicParsing
                Assert-Payload $archive $release.payload
                $stage = Join-Path $temporary 'files'
                New-Item -ItemType Directory -Path $stage | Out-Null
                Expand-SafeArchive $archive $stage
                if (-not (Test-Path -LiteralPath (Join-Path $stage 'eglantine.exe') -PathType Leaf)) { throw 'Update has no emulator executable' }
                $destination = Join-Path (Join-Path $root 'versions') $release.payload.sha256
                if (-not (Test-Path -LiteralPath $destination)) { Move-Item -LiteralPath $stage -Destination $destination }
                if (-not (Test-Path -LiteralPath (Join-Path $destination 'eglantine.exe') -PathType Leaf)) { throw 'Existing payload directory is incomplete' }
            }
            $next = @{ version=$release.version; sha256=$release.payload.sha256; published_at=$release.published_at }
            Save-Current $next
            $current = $next
            Write-UpdateLog ('Updated to ' + $release.version)
        }
    } catch { Write-UpdateLog ('Update unavailable; using installed version: ' + $_.Exception.Message) }
    $exe = Join-Path (Join-Path (Join-Path $root 'versions') $current.sha256) 'eglantine.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'The installed emulator is missing; reinstall Eglantine' }
    $arguments = if ($ArgsBase64) { [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($ArgsBase64)) } else { '' }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $exe; $start.WorkingDirectory = [IO.Path]::GetDirectoryName($exe)
    $start.Arguments = $arguments; $start.UseShellExecute = $false
    [Diagnostics.Process]::Start($start) | Out-Null
    # Preserve payloads still used by an already-running emulator.
    $running = @(Get-Process -Name eglantine -ErrorAction SilentlyContinue)
    foreach ($old in Get-ChildItem -LiteralPath (Join-Path $root 'versions') -Directory) {
        if ($old.Name -eq $current.sha256) { continue }
        $used = $false
        foreach ($process in $running) {
            try { if (-not $process.Path -or $process.Path.StartsWith($old.FullName + '\', [StringComparison]::OrdinalIgnoreCase)) { $used = $true } }
            catch { $used = $true }
        }
        if (-not $used) { try { Remove-Item -LiteralPath $old.FullName -Recurse -Force } catch {} }
    }
} catch {
    Write-UpdateLog $_.Exception.Message
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show($_.Exception.Message, $config.title) | Out-Null
} finally {
    if ($temporary -and (Test-Path -LiteralPath $temporary)) { try { Remove-Item -LiteralPath $temporary -Recurse -Force } catch {} }
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
