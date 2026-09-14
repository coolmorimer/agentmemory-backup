[CmdletBinding()]
param(
    [switch]$SkipCodexPlugin,
    [switch]$SkipAutostart
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path $PSScriptRoot -Parent
$dataDirectory = Join-Path $env:USERPROFILE '.agentmemory'
$binDirectory = Join-Path $dataDirectory 'bin'
$iiiVersion = '0.11.2'

foreach ($command in @('node', 'npm')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required. Install Node.js 20 or newer first."
    }
}
$nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
if ($nodeMajor -lt 20) { throw 'Node.js 20 or newer is required.' }

& npm install --global "@agentmemory/agentmemory@0.9.29"
if ($LASTEXITCODE -ne 0) { throw 'AgentMemory npm installation failed.' }

New-Item -ItemType Directory -Force -Path $dataDirectory, $binDirectory | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $dataDirectory '.env'))) {
    & agentmemory.cmd init
    if ($LASTEXITCODE -ne 0) { throw 'AgentMemory configuration initialization failed.' }
}

$iiiPath = Join-Path $binDirectory 'iii.exe'
if (-not (Test-Path -LiteralPath $iiiPath -PathType Leaf)) {
    $downloadDirectory = Join-Path $env:TEMP ('agentmemory-iii-' + [guid]::NewGuid().ToString('N'))
    $zipPath = Join-Path $downloadDirectory 'iii.zip'
    $checksumPath = Join-Path $downloadDirectory 'iii.sha256'
    New-Item -ItemType Directory -Path $downloadDirectory | Out-Null
    try {
        $releaseBase = "https://github.com/iii-hq/iii/releases/download/iii%2Fv$iiiVersion"
        Invoke-WebRequest -Uri "$releaseBase/iii-x86_64-pc-windows-msvc.zip" -OutFile $zipPath
        Invoke-WebRequest -Uri "$releaseBase/iii-x86_64-pc-windows-msvc.sha256" -OutFile $checksumPath
        $expected = ([regex]::Match((Get-Content -LiteralPath $checksumPath -Raw), '[A-Fa-f0-9]{64}')).Value.ToLowerInvariant()
        $actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($expected) -or $actual -ne $expected) {
            throw 'iii download checksum verification failed.'
        }
        Expand-Archive -LiteralPath $zipPath -DestinationPath $downloadDirectory
        $downloadedExe = Get-ChildItem -LiteralPath $downloadDirectory -Recurse -Filter 'iii.exe' -File | Select-Object -First 1
        if (-not $downloadedExe) { throw 'iii.exe was not found in the verified archive.' }
        Copy-Item -LiteralPath $downloadedExe.FullName -Destination $iiiPath -Force
    } finally {
        if (Test-Path -LiteralPath $downloadDirectory) {
            $resolvedDownload = [System.IO.Path]::GetFullPath($downloadDirectory)
            $resolvedTemp = [System.IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
            if (-not $resolvedDownload.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove an unexpected path: $resolvedDownload"
            }
            Remove-Item -LiteralPath $downloadDirectory -Recurse -Force
        }
    }
}

Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Start-AgentMemory.ps1') -Destination (Join-Path $dataDirectory 'start-agentmemory.ps1') -Force
& (Join-Path $PSScriptRoot 'Patch-AgentMemoryDashboard.ps1') -RepositoryRoot $repositoryRoot

if (-not $SkipAutostart) {
    $startupDirectory = [Environment]::GetFolderPath('Startup')
    $shortcutPath = Join-Path $startupDirectory 'AgentMemory.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = 'powershell.exe'
    $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $dataDirectory 'start-agentmemory.ps1') + '"'
    $shortcut.WorkingDirectory = $dataDirectory
    $shortcut.WindowStyle = 7
    $shortcut.Save()
}

if (-not $SkipCodexPlugin) {
    if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
        throw 'Codex CLI is required to install the Codex plugin. Re-run with -SkipCodexPlugin to omit it.'
    }
    & codex plugin marketplace add $repositoryRoot
    if ($LASTEXITCODE -ne 0) {
        $marketplaces = (& codex plugin marketplace list 2>&1 | Out-String)
        if ($marketplaces -notmatch 'agentmemory-backup') { throw 'Unable to register the local AgentMemory marketplace.' }
    }
    & codex plugin add 'agentmemory@agentmemory-backup'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to install the AgentMemory Codex plugin.' }
    & node (Join-Path $PSScriptRoot 'Trust-AgentMemoryHooks.mjs') $repositoryRoot
    if ($LASTEXITCODE -ne 0) { throw 'Unable to trust the AgentMemory lifecycle hooks.' }
}

$restartScript = Join-Path $dataDirectory 'dashboard\restart.ps1'
if (Test-Path -LiteralPath (Join-Path $dataDirectory 'worker.pid')) {
    & $restartScript
} else {
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $dataDirectory 'start-agentmemory.ps1'))
}

$deadline = (Get-Date).AddSeconds(45)
do {
    Start-Sleep -Seconds 1
    try { $health = Invoke-RestMethod -Uri 'http://localhost:3111/agentmemory/health' -TimeoutSec 3 } catch { $health = $null }
} until ($health.status -eq 'healthy' -or (Get-Date) -gt $deadline)
if ($health.status -ne 'healthy') { throw 'AgentMemory did not become healthy within 45 seconds. Check ~/.agentmemory/daemon.log.' }

Write-Host 'AgentMemory is healthy.'
Write-Host 'Dashboard: http://localhost:3113'
Write-Host 'Add the OpenRouter key in the dashboard. The key is stored only in ~/.agentmemory/.env.'
