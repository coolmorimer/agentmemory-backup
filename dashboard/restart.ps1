$ErrorActionPreference = 'Stop'
Start-Sleep -Seconds 2
$workerId = [int](Get-Content -LiteralPath "$PSScriptRoot\..\worker.pid")
$worker = Get-CimInstance Win32_Process -Filter "ProcessId=$workerId"
if ($worker -and $worker.Name -eq 'node.exe' -and $worker.CommandLine -match '@agentmemory[\\/]agentmemory[\\/]dist[\\/]cli.mjs') {
    Stop-Process -Id $workerId
    Start-Sleep -Seconds 2
}
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',"$PSScriptRoot\..\start-agentmemory.ps1")
