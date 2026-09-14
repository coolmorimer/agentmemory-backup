param(
    [switch]$Install,
    [ValidateSet("minimal", "recommended", "embeddings")]
    [string]$Profile = "minimal",
    [string]$OllamaExecutable = ""
)

$models = switch ($Profile) {
    "minimal" { @("qwen2.5-coder:7b", "qwen3-embedding:0.6b") }
    "embeddings" { @("qwen3-embedding:0.6b", "qwen3-embedding:4b") }
    "recommended" {
        @(
            "qwen2.5-coder:7b",
            "qwen2.5-coder:14b",
            "qwen3:14b",
            "gemma3:12b",
            "deepseek-coder-v2:16b",
            "qwen3-embedding:0.6b",
            "qwen3-embedding:4b"
        )
    }
}

if ($OllamaExecutable) {
    $ollamaCommand = Get-Item -LiteralPath $OllamaExecutable -ErrorAction Stop
} else {
    $ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
}

if (-not $ollamaCommand) {
    throw "Ollama is not installed or is not available on PATH. Pass -OllamaExecutable if needed."
}

if (-not $Install) {
    Write-Host "Dry run. Re-run with -Install to download the selected models:"
    $models | ForEach-Object { Write-Host "ollama pull $_" }
    exit 0
}

foreach ($model in $models) {
    & $ollamaCommand pull $model
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to pull $model"
    }
}
