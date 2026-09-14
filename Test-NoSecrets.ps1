[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoDirectory = $PSScriptRoot
$patterns = [ordered]@{
    'GitHub token' = '(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}'
    'OpenRouter key' = '(?<![A-Za-z0-9])sk-or-v1-[A-Za-z0-9_-]{20,}'
    'Anthropic key' = '(?<![A-Za-z0-9])sk-ant-[A-Za-z0-9_-]{20,}'
    'OpenAI-style key' = '(?<![A-Za-z0-9])sk-(?!or-v1-|ant-)[A-Za-z0-9_-]{20,}'
    'AWS access key' = '(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])'
    'Private key' = '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
}

$files = & git -C $repoDirectory ls-files --cached --others --exclude-standard
if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate repository files.' }
$findings = [System.Collections.Generic.List[string]]::new()
foreach ($relativePath in $files) {
    if ($relativePath -eq 'Test-NoSecrets.ps1') { continue }
    $path = Join-Path $repoDirectory $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ($bytes -contains 0) { continue }
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    foreach ($entry in $patterns.GetEnumerator()) {
        if ([regex]::IsMatch($text, $entry.Value)) {
            $findings.Add("$relativePath : possible $($entry.Key)")
        }
    }
}

if ($findings.Count -gt 0) {
    $findings | ForEach-Object { Write-Error $_ }
    throw "Secret scan failed with $($findings.Count) finding(s)."
}
Write-Host "Secret scan passed for $($files.Count) repository file(s)."
