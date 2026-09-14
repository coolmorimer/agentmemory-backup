# Codex App Server

`CodexAppServerAgent` starts `codex app-server` as a JSON-RPC subprocess without a shell. It performs
the initialize handshake, creates or resumes the durable thread attached to a task, streams turn
notifications, and returns typed thread/turn identifiers for persistence. Approval is never silently
broadened and sandbox settings are explicit.

Regenerate compatibility fixtures against the installed CLI with:

```powershell
.\scripts\generate-codex-schema.ps1
```

The fake App Server in `tests/fixtures` validates framing and lifecycle in CI without an inference
charge. A local initialize smoke can validate the installed executable without starting a paid turn.
Retry continuity uses `codex_threads` and `codex_turns`; task cancellation prevents a late agent result
from being committed.
