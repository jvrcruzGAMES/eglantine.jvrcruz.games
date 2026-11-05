$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile('/repo/windows/updater.ps1', [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
# Load the actual updater functions without running its GUI/network startup path.
$ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst]}, $false) | ForEach-Object { Invoke-Expression $_.Extent.Text }
$root = Join-Path ([IO.Path]::GetTempPath()) ('updater-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
try {
    Save-Current @{ version='old'; sha256=('a' * 64); published_at='2026-11-05T00:00:00Z' }
    if ((Read-Current).version -ne 'old') { throw 'Initial pointer failed' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach ($name in @('../escape.exe', '..\escape.exe', 'folder/.. /escape.exe', 'file:ads', '/absolute.exe')) {
        $zipPath = Join-Path $root ([Guid]::NewGuid().ToString('N') + '.zip')
        $zip = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Create)
        $entry = $zip.CreateEntry($name)
        $writer = New-Object IO.StreamWriter($entry.Open()); $writer.Write('bad'); $writer.Dispose(); $zip.Dispose()
        $dest = Join-Path $root ('stage-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $dest | Out-Null
        $rejected = $false
        try { Expand-SafeArchive $zipPath $dest } catch { $rejected = $true }
        if (-not $rejected) { throw ('Unsafe zip accepted: ' + $name) }
        if ((Read-Current).version -ne 'old') { throw 'Failed extraction changed installed version' }
    }
    $zipPath = Join-Path $root 'good.zip'
    $zip = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Create)
    $entry = $zip.CreateEntry('eglantine.exe')
    $writer = New-Object IO.StreamWriter($entry.Open()); $writer.Write('emulator fixture'); $writer.Dispose(); $zip.Dispose()
    $metadata = @{bytes=(Get-Item $zipPath).Length; sha256=(Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()}
    Assert-Payload $zipPath $metadata
    $metadata.sha256 = '0' * 64
    $rejected = $false
    try { Assert-Payload $zipPath $metadata } catch { $rejected = $true }
    if (-not $rejected -or (Read-Current).version -ne 'old') { throw 'Bad checksum changed installed payload' }
    $dest = Join-Path $root 'valid'
    New-Item -ItemType Directory -Path $dest | Out-Null
    Expand-SafeArchive $zipPath $dest
    if ((Get-Content -Raw -LiteralPath (Join-Path $dest 'eglantine.exe')) -ne 'emulator fixture') { throw 'Valid zip extraction failed' }
    Save-Current @{ version='new'; sha256=('b' * 64); published_at='2026-11-05T01:00:00Z' }
    if ((Read-Current).version -ne 'new') { throw 'Atomic pointer replacement failed' }
    $config = [pscustomobject]@{feed='https://example.test/windows/updates/latest.json'; channel='stable'; package='eglantine'}
    $release = [pscustomobject]@{schema=1; channel='stable'; package='eglantine'; platform='windows'; payload=[pscustomobject]@{sha256=('a'*64); bytes=42; url='/windows/releases/test/app.zip'}}
    if ((Get-UpdateUri $config $release).AbsoluteUri -ne 'https://example.test/windows/releases/test/app.zip') { throw 'Valid manifest rejected' }
    foreach ($bad in @('https://evil.test/windows/releases/test/app.zip', '/nightly/windows/releases/test/app.zip', 'http://example.test/windows/releases/test/app.zip')) {
        $release.payload.url = $bad
        $rejected = $false
        try { Get-UpdateUri $config $release | Out-Null } catch { $rejected = $true }
        if (-not $rejected) { throw 'Unexpected download origin/path accepted' }
    }
    $release.payload.url = '/windows/releases/test/app.zip'; $release.channel='nightly'
    $rejected = $false
    try { Get-UpdateUri $config $release | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw 'Cross-channel update accepted' }
    Write-Output 'Updater syntax, safe extraction, rejected traversal/ADS and atomic pointer tests passed.'
} finally { Remove-Item -LiteralPath $root -Recurse -Force }
