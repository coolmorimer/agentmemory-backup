param(
    [string]$InstallerPath = "D:\Installers\OllamaSetup.exe",
    [string]$InstallRoot = "D:\Apps\Ollama",
    [string]$ModelRoot = "D:\AI\Ollama\models",
    [string]$DownloadUrl = "https://github.com/ollama/ollama/releases/download/v0.33.2/OllamaSetup.exe",
    [long]$ExpectedSize = 1565765264,
    [string]$ExpectedSha256 = "5a91c1cf92480e28a84cd99e437219be719df5a50d5fa0fd5fe5b5c4a122f506",
    [switch]$ForceInstall,
    [switch]$SkipAutostart
)

$ErrorActionPreference = "Stop"
$installerDirectory = Split-Path -Parent $InstallerPath
New-Item -ItemType Directory -Force -Path $installerDirectory | Out-Null
if (-not (Test-Path -LiteralPath $InstallerPath)) {
    $aria = Get-Command aria2c -ErrorAction SilentlyContinue
    if ($aria) {
        $installerName = Split-Path -Leaf $InstallerPath
        & $aria --continue=true --max-connection-per-server=8 --split=8 `
            --min-split-size=16M --file-allocation=none --auto-file-renaming=false `
            --dir=$installerDirectory --out=$installerName $DownloadUrl
    } else {
        & curl.exe --fail --location --retry 10 --continue-at - `
            --output $InstallerPath $DownloadUrl
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Ollama installer download failed."
    }
}
$installer = Get-Item -LiteralPath $InstallerPath -ErrorAction Stop
if ($installer.Length -ne $ExpectedSize) {
    throw "Installer size mismatch: expected $ExpectedSize, got $($installer.Length)."
}

$actualHash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) {
    throw "Installer SHA-256 mismatch. Refusing to execute it."
}
$signature = Get-AuthenticodeSignature -LiteralPath $installer.FullName
if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid) {
    throw "Installer Authenticode signature is not valid: $($signature.Status)."
}

New-Item -ItemType Directory -Force -Path $InstallRoot, $ModelRoot | Out-Null
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $ModelRoot, "User")
$env:OLLAMA_MODELS = $ModelRoot

$ollamaConfigRoot = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".ollama"
if (Test-Path -LiteralPath $ollamaConfigRoot) {
    $configItem = Get-Item -LiteralPath $ollamaConfigRoot -Force
    if (($configItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw (
            "Ollama refuses to start from an untrusted .ollama junction. " +
            "Move the junction aside and create a normal directory at $ollamaConfigRoot; " +
            "model blobs will still stay at $ModelRoot."
        )
    }
} else {
    New-Item -ItemType Directory -Path $ollamaConfigRoot | Out-Null
}

$ollama = Join-Path $InstallRoot "ollama.exe"
if ($ForceInstall -or -not (Test-Path -LiteralPath $ollama)) {
    $process = Start-Process -FilePath $installer.FullName -ArgumentList @(
        "/VERYSILENT",
        "/NORESTART",
        "/SUPPRESSMSGBOXES",
        "/DIR=`"$InstallRoot`""
    ) -PassThru
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Ollama installer failed with exit code $($process.ExitCode)."
    }
}

if (-not (Test-Path -LiteralPath $ollama)) {
    $ollama = Get-ChildItem -LiteralPath $InstallRoot -Filter ollama.exe -Recurse |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $ollama) {
    throw "Installation completed, but ollama.exe was not found under $InstallRoot."
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathEntries = @($userPath -split ";" | Where-Object { $_ })
if ($InstallRoot -notin $pathEntries) {
    [Environment]::SetEnvironmentVariable(
        "Path",
        (($pathEntries + $InstallRoot) -join ";"),
        "User"
    )
}

if (-not $SkipAutostart) {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $ollama -Argument "serve" `
        -WorkingDirectory $InstallRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
    $trigger.Delay = "PT10S"
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive `
        -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName "AutoDev Ollama" -Action $action -Trigger $trigger `
        -Principal $principal -Settings $taskSettings -Description (
            "Start Ollama for AutoDev; model blobs are stored in $ModelRoot"
        ) -Force | Out-Null
}

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
} catch {
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    $ready = $false
    foreach ($attempt in 1..30) {
        Start-Sleep -Milliseconds 500
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch {
            # Continue until the bounded readiness deadline.
        }
    }
    if (-not $ready) {
        throw "Ollama was installed but did not become ready on port 11434."
    }
}

Write-Host "Ollama is ready. Binaries: $InstallRoot; models: $ModelRoot"
Write-Output $ollama
