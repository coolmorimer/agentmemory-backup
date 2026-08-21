[CmdletBinding()]
param(
    [ValidateRange(1, 24)]
    [int]$EveryHours = 1
)

$ErrorActionPreference = 'Stop'
$taskName = 'AgentMemory GitHub Backup'
$backupScript = Join-Path $PSScriptRoot 'Backup-Memory.ps1'
$argument = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $backupScript
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(5)) -RepetitionInterval (New-TimeSpan -Hours $EveryHours)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Description 'Export AgentMemory and push changes to the private GitHub backup repository.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Automatic backup installed: every $EveryHours hour(s), while $user is signed in."

