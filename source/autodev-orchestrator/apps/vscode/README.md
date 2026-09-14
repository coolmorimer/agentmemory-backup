# AutoDev Orchestrator for VS Code

The extension adds an AutoDev activity-bar view for projects, provider state, installed Ollama
models, model selection, OpenRouter setup, goal creation, independent task pause/resume,
task stop/delete actions, and host-worker control.

Default endpoints are `http://127.0.0.1:8000` and `http://127.0.0.1:5173`. Change them in VS Code
Settings under **AutoDev Orchestrator** when the services run elsewhere.

## Install

```powershell
npm ci
npm run package
code --install-extension .\autodev-orchestrator-vscode-0.2.3.vsix --force
```

Reload the VS Code window after the first install. The AutoDev icon then appears in the Activity Bar.
The extension stores the entered OpenRouter key in VS Code SecretStorage and sends it over the local
API to AutoDev's encrypted server-side credential vault; neither tree views nor API responses reveal
the key.
