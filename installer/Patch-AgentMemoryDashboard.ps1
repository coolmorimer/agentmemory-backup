[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$RepositoryRoot
)

$ErrorActionPreference = 'Stop'
$npmRoot = (& npm root --global).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($npmRoot)) {
    throw 'Unable to locate the global npm directory.'
}

$distDirectory = Join-Path $npmRoot '@agentmemory\agentmemory\dist'
if (-not (Test-Path -LiteralPath $distDirectory -PathType Container)) {
    throw "AgentMemory package is missing: $distDirectory"
}

$dashboardSource = Join-Path $RepositoryRoot 'dashboard'
$dashboardTarget = Join-Path $env:USERPROFILE '.agentmemory\dashboard'
New-Item -ItemType Directory -Force -Path $dashboardTarget | Out-Null
Copy-Item -LiteralPath (Join-Path $dashboardSource 'settings.mjs') -Destination $dashboardTarget -Force
Copy-Item -LiteralPath (Join-Path $dashboardSource 'restart.ps1') -Destination $dashboardTarget -Force

$settingsUri = ([Uri](Join-Path $dashboardTarget 'settings.mjs')).AbsoluteUri
$importLine = "import { injectSettings, settingsRoute } from '$settingsUri';`n"
$htmlOriginal = 'html: template.replaceAll(VIEWER_NONCE_PLACEHOLDER, nonce).replaceAll(VIEWER_VERSION_PLACEHOLDER, VERSION),'
$htmlPatched = 'html: injectSettings(template.replaceAll(VIEWER_NONCE_PLACEHOLDER, nonce).replaceAll(VIEWER_VERSION_PLACEHOLDER, VERSION), nonce),'
$proxyOriginal = "`t`ttry {`n`t`t`tawait proxyToRestApi(resolvedRestPort"
$proxyPatched = "`t`tif (await settingsRoute(req, res)) return;`n$proxyOriginal"

$targets = Get-ChildItem -LiteralPath $distDirectory -Filter '*.mjs' -File | Where-Object {
    Select-String -LiteralPath $_.FullName -SimpleMatch 'function renderViewerDocument()' -Quiet
}
if (-not $targets) {
    throw 'AgentMemory viewer runtime was not found. Expected version 0.9.29.'
}

foreach ($target in $targets) {
    $content = [System.IO.File]::ReadAllText($target.FullName)
    if ($content -notmatch "from 'file:///C:/Users/.+/.agentmemory/dashboard/settings.mjs'" ) {
        $content = $importLine + $content
    }
    if ($content.Contains($htmlOriginal)) {
        $content = $content.Replace($htmlOriginal, $htmlPatched)
    }
    if ($content.Contains($proxyOriginal) -and -not $content.Contains('if (await settingsRoute(req, res)) return;')) {
        $content = $content.Replace($proxyOriginal, $proxyPatched)
    }
    if (-not $content.Contains($htmlPatched) -or -not $content.Contains('if (await settingsRoute(req, res)) return;')) {
        throw "Dashboard patch could not be applied to $($target.Name)."
    }
    [System.IO.File]::WriteAllText($target.FullName, $content, [System.Text.UTF8Encoding]::new($false))
    & node --check $target.FullName
    if ($LASTEXITCODE -ne 0) { throw "Patched JavaScript is invalid: $($target.FullName)" }
}

Write-Host "Dashboard OpenRouter settings installed in $($targets.Count) runtime file(s)."
