param(
    [string]$OutputDirectory = "generated/codex",
    [switch]$Experimental
)

$arguments = @("app-server", "generate-json-schema", "--out", $OutputDirectory)
if ($Experimental) {
    $arguments += "--experimental"
}

& codex @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Codex schema generation failed with exit code $LASTEXITCODE"
}

