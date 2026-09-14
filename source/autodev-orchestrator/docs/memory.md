# Engineering memory

Memory is accessed through the `MemoryProvider` protocol. The AgentMemory HTTP and MCP adapters support
search and store without coupling core orchestration to the service package. Before coding, the engine
retrieves project-scoped and global candidates, deduplicates them, and passes only bounded, redacted
context. After a verified commit, it stores a compact task-outcome experience; memory failure is
audited but cannot invalidate deterministic task evidence.

Configure `AUTODEV_AGENTMEMORY_BASE_URL` and, if required, `AGENTMEMORY_SECRET`. The read-only operator
endpoint is `/api/memory/search?query=...&project=...`. Never store credentials, raw `.env` content,
large source dumps, or untrusted repository instructions as authoritative guidance.
