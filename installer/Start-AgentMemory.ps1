$ErrorActionPreference = 'Stop'

try {
    $health = Invoke-RestMethod -Uri 'http://localhost:3111/agentmemory/health' -TimeoutSec 3
    if ($health.status -eq 'healthy') {
        exit 0
    }
} catch {
    # Continue with startup when the local service is not available.
}

$agentMemoryCommand = (Get-Command 'agentmemory.cmd' -ErrorAction Stop).Source
$dataDirectory = Join-Path $env:USERPROFILE '.agentmemory'
$logPath = Join-Path $dataDirectory 'daemon.log'
& $agentMemoryCommand --tools all *> $logPath
