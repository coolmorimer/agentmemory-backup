[CmdletBinding()]
param(
    [string]$ApiUrl = 'http://localhost:3111',
    [ValidateSet('merge', 'replace')]
    [string]$Strategy = 'merge',
    [switch]$NoPull
)

$ErrorActionPreference = 'Stop'
$repoDir = $PSScriptRoot
$exportPath = Join-Path $repoDir 'memory-export.json'

try {
    $health = Invoke-RestMethod -Uri "$ApiUrl/agentmemory/health" -TimeoutSec 10
} catch {
    throw "AgentMemory is unavailable at $ApiUrl. Install and start AgentMemory first. $($_.Exception.Message)"
}
if ($health.status -ne 'healthy') {
    throw "AgentMemory reported status '$($health.status)'."
}

if (-not $NoPull) {
    & git -C $repoDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw 'git pull failed.' }
}

if (-not (Test-Path -LiteralPath $exportPath -PathType Leaf)) {
    throw "Backup file not found: $exportPath"
}

$exportData = Get-Content -LiteralPath $exportPath -Raw | ConvertFrom-Json
$body = @{ exportData = $exportData; strategy = $Strategy } | ConvertTo-Json -Depth 100
$result = Invoke-RestMethod -Uri "$ApiUrl/agentmemory/import" -Method Post -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 300
if ($result.success -ne $true) {
    throw "AgentMemory restore failed: $($result.error)"
}

$searchBody = @{ query = 'memory'; limit = 1 } | ConvertTo-Json
$null = Invoke-RestMethod -Uri "$ApiUrl/agentmemory/smart-search" -Method Post -ContentType 'application/json' -Body $searchBody -TimeoutSec 30
Write-Host "Restore complete using strategy '$Strategy'. AgentMemory search responded successfully."
