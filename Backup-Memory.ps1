[CmdletBinding()]
param(
    [string]$ApiUrl = 'http://localhost:3111',
    [switch]$NoPush
)

$ErrorActionPreference = 'Stop'
$repoDir = $PSScriptRoot
$exportPath = Join-Path $repoDir 'memory-export.json'
$metaPath = Join-Path $repoDir 'backup-meta.json'
$tempPath = Join-Path $repoDir 'memory-export.json.tmp'

function Assert-AgentMemoryRunning {
    try {
        $health = Invoke-RestMethod -Uri "$ApiUrl/agentmemory/health" -TimeoutSec 10
    } catch {
        throw "AgentMemory is unavailable at $ApiUrl. Start it and try again. $($_.Exception.Message)"
    }
    if ($health.status -ne 'healthy') {
        throw "AgentMemory reported status '$($health.status)'."
    }
}

function Assert-NoPlaintextSecrets {
    param([Parameter(Mandatory)][string]$Text)

    $patterns = [ordered]@{
        'GitHub token' = '(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}'
        'OpenAI-style key' = '(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}'
        'Anthropic key' = '(?<![A-Za-z0-9])sk-ant-[A-Za-z0-9_-]{20,}'
        'AWS access key' = '(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])'
        'Private key' = '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
        'Credential assignment' = '(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[=:]\s*["'']?[A-Za-z0-9_./+\-=]{16,}'
    }

    foreach ($entry in $patterns.GetEnumerator()) {
        if ([regex]::IsMatch($Text, $entry.Value)) {
            throw "Backup blocked: possible $($entry.Key) found in the exported memory. Remove it from AgentMemory before backup."
        }
    }
}

Assert-AgentMemoryRunning
$exportData = Invoke-RestMethod -Uri "$ApiUrl/agentmemory/export" -TimeoutSec 120
if ($exportData.error) {
    throw "AgentMemory export failed: $($exportData.error)"
}

$exportData.PSObject.Properties.Remove('exportedAt')
$json = $exportData | ConvertTo-Json -Depth 100
Assert-NoPlaintextSecrets -Text $json
$newContent = $json + [Environment]::NewLine
$oldContent = if (Test-Path -LiteralPath $exportPath -PathType Leaf) {
    [System.IO.File]::ReadAllText($exportPath)
} else {
    $null
}

$observationCount = 0
if ($exportData.observations) {
    foreach ($property in $exportData.observations.PSObject.Properties) {
        $observationCount += @($property.Value).Count
    }
}
$meta = [ordered]@{
    backedUpAt = (Get-Date).ToUniversalTime().ToString('o')
    agentMemoryVersion = $exportData.version
    sessions = @($exportData.sessions).Count
    observations = $observationCount
    memories = @($exportData.memories).Count
    lessons = @($exportData.lessons).Count
}
if ($newContent -cne $oldContent) {
    [System.IO.File]::WriteAllText($tempPath, $newContent, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tempPath -Destination $exportPath -Force
    $metaJson = $meta | ConvertTo-Json
    [System.IO.File]::WriteAllText($metaPath, $metaJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
}

& git -C $repoDir add -- memory-export.json backup-meta.json
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }

& git -C $repoDir diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Memory is already up to date.'
} elseif ($LASTEXITCODE -eq 1) {
    $message = 'Memory backup ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')
    & git -C $repoDir commit -m $message -- memory-export.json backup-meta.json
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
} else {
    throw 'Unable to compare the staged backup.'
}

if (-not $NoPush) {
    & git -C $repoDir push origin HEAD
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
}

Write-Host "Backup complete: $($meta.sessions) sessions, $($meta.observations) observations, $($meta.memories) memories, $($meta.lessons) lessons."
