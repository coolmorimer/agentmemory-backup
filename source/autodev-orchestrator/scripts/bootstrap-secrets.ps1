param(
    [string]$EnvironmentFile = (Join-Path $PSScriptRoot "..\.env")
)

$ErrorActionPreference = "Stop"
$resolvedEnvironmentFile = [System.IO.Path]::GetFullPath($EnvironmentFile)
$exampleFile = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.env.example"))

if (-not (Test-Path -LiteralPath $resolvedEnvironmentFile)) {
    Copy-Item -LiteralPath $exampleFile -Destination $resolvedEnvironmentFile
}

$content = [System.IO.File]::ReadAllText($resolvedEnvironmentFile)
$existing = [regex]::Match(
    $content,
    "(?m)^AUTODEV_CREDENTIAL_KEY=(?<value>[^\r\n]+)$"
)
if ($existing.Success -and $existing.Groups["value"].Value.Trim()) {
    Write-Host "AutoDev credential vault is already configured."
    exit 0
}

$bytes = [byte[]]::new(32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$key = [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")
$line = "AUTODEV_CREDENTIAL_KEY=$key"

if ($content -match "(?m)^AUTODEV_CREDENTIAL_KEY=.*$") {
    $content = [regex]::Replace($content, "(?m)^AUTODEV_CREDENTIAL_KEY=.*$", $line)
} else {
    $separator = if ($content.EndsWith("`n")) { "" } else { [Environment]::NewLine }
    $content = "$content$separator$line$([Environment]::NewLine)"
}

[System.IO.File]::WriteAllText(
    $resolvedEnvironmentFile,
    $content,
    [System.Text.UTF8Encoding]::new($false)
)
Write-Host "AutoDev credential vault key was generated in the ignored .env file."
