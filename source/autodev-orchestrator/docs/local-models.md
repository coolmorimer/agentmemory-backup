# Local models

Local execution is the default and paid routing is disabled. Suggested workstation profiles live in
`config/models.yaml`: small Qwen coder models for fast work, larger coder/reasoning models for
implementation and planning, Gemma for visual QA, and dedicated embedding models.

The supported Windows bootstrap deliberately keeps both binaries and model blobs away from a full
system drive. Its defaults are `D:\Apps\Ollama` and `D:\AI\Ollama\models`. It verifies the pinned
official installer's byte length and SHA-256 before execution, persists `OLLAMA_MODELS`, starts the
local API, registers the `AutoDev Ollama` logon task, and checks port 11434:

```powershell
.\scripts\install-ollama.ps1
.\scripts\bootstrap-local-models.ps1 -Install -Profile minimal `
  -OllamaExecutable D:\Apps\Ollama\ollama.exe
```

Profiles are `minimal` (coder 7B plus embedding 0.6B), `embeddings`, and `recommended` (the complete
seven-model workstation pool). Pulls run sequentially so only one large model download/inference
load is active at once. After pulling, use `POST /api/models/discover?provider=ollama` and select an
installed model through the dashboard or VS Code.

The verified workstation baseline is `qwen2.5-coder:7b` for implementation advice and
`qwen3-embedding:0.6b` for online embeddings. This is the intentional `minimal` profile: it proves
real GPU inference and leaves the larger optional pool as an explicit operator choice.

AutoDev may also use LM Studio or another local
OpenAI-compatible endpoint through `config/providers.yaml`. Missing Ollama is non-fatal: health is
reported as unavailable and the router can use another policy-eligible local adapter. GPU-heavy local
inference should remain single-concurrency on a 12 GB card; Codex workers can run independently.
