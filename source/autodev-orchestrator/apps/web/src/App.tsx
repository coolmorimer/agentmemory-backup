import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Project = {
  id: string;
  name: string;
  repository_path: string;
  privacy_level: string;
  status: string;
};

type Task = {
  id: string;
  key: string;
  title: string;
  status: string;
  attempts: number;
  priority: number;
};

type Overview = {
  project: Project;
  tasks: Task[];
  events: Array<{ event: string; actor: string; created_at: string; details: unknown }>;
  deployments: Array<{ id: string; environment: string; release_ref: string; status: string }>;
};

type Summary = {
  projects: Record<string, number>;
  tasks: Record<string, number>;
  open_qa_findings: number;
  active_deployments: number;
};

type ModelStat = {
  provider: string;
  model: string;
  calls: number;
  success_rate: number;
  average_latency_seconds: number;
  tokens: number;
  health: string;
  requests_remaining: number | null;
};

type ProviderConfig = {
  name: string;
  kind: "ollama" | "openai_compatible" | "codex_app_server";
  enabled: boolean;
  base_url: string;
  api_key_env: string | null;
  billing_mode: "local" | "free" | "paid" | "gateway";
  accepts_private_code: boolean;
  timeout_seconds: number;
  credential_configured: boolean;
  vault_available: boolean;
};

type ConfiguredModel = {
  id: string;
  provider: string;
  display_name: string;
  local: boolean;
  enabled: boolean;
  installed: boolean;
  roles: string[];
  selected_for: string[];
};

type LiveEvent = {
  id: string;
  name: string;
  project_id: string | null;
  task_id: string | null;
  occurred_at: string;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `Request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const total = (values: Record<string, number>) =>
  Object.values(values).reduce((sum, value) => sum + value, 0);

function statusTone(status: string) {
  if (["COMPLETED", "HEALTHY", "APPROVED"].includes(status)) return "good";
  if (["FAILED", "CANCELLED", "COOLDOWN", "ROLLBACK_FAILED"].includes(status)) return "bad";
  if (["BLOCKED", "FIX_REQUIRED", "DEGRADED", "PAUSED"].includes(status)) return "warn";
  return "active";
}

const activeTaskStatuses = new Set(["RUNNING", "TESTING", "REVIEWING", "APPROVED"]);
const cancellableTaskStatuses = new Set(["RUNNING", "TESTING", "REVIEWING"]);
const pausableTaskStatuses = new Set([
  "DRAFT", "READY", "WAITING_DEPENDENCY", "WAITING_PROVIDER", "RUNNING", "TESTING",
  "REVIEWING", "FIX_REQUIRED", "BLOCKED"
]);

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [modelStats, setModelStats] = useState<ModelStat[]>([]);
  const [providers, setProviders] = useState<ProviderConfig[]>([]);
  const [configuredModels, setConfiguredModels] = useState<ConfiguredModel[]>([]);
  const [providerDraftReady, setProviderDraftReady] = useState(false);
  const [openRouter, setOpenRouter] = useState({
    enabled: false,
    base_url: "https://openrouter.ai/api/v1",
    api_key: "",
    accepts_private_code: false
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", repository_path: "", goal: "" });

  const refresh = useCallback(async () => {
    try {
      const [nextProjects, nextSummary, nextModelStats, nextProviders, nextConfiguredModels] = await Promise.all([
        api<Project[]>("/api/projects"),
        api<Summary>("/api/dashboard/summary"),
        api<ModelStat[]>("/api/dashboard/models"),
        api<ProviderConfig[]>("/api/providers"),
        api<ConfiguredModel[]>("/api/models")
      ]);
      setProjects(nextProjects);
      setSummary(nextSummary);
      setModelStats(nextModelStats);
      setProviders(nextProviders);
      setConfiguredModels(nextConfiguredModels);
      setSelectedId((current) => current ?? nextProjects[0]?.id ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load dashboard");
    }
  }, []);

  useEffect(() => {
    if (providerDraftReady) return;
    const config = providers.find((provider) => provider.name === "openrouter");
    if (!config) return;
    setOpenRouter((current) => ({
      ...current,
      enabled: config.enabled,
      base_url: config.base_url,
      accepts_private_code: config.accepts_private_code
    }));
    setProviderDraftReady(true);
  }, [providerDraftReady, providers]);

  const refreshOverview = useCallback(async () => {
    if (!selectedId) {
      setOverview(null);
      return;
    }
    try {
      setOverview(await api<Overview>(`/api/dashboard/projects/${selectedId}`));
    } catch (reason) {
      if (reason instanceof Error && reason.message === "project not found") {
        setOverview(null);
        return;
      }
      setError(reason instanceof Error ? reason.message : "Unable to load project");
    }
  }, [selectedId]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    void refreshOverview();
  }, [refreshOverview]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/events`);
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as LiveEvent;
      setEvents((current) => [event, ...current].slice(0, 20));
      if (event.name === "project.deleted" && event.project_id === selectedId) {
        setOverview(null);
        setSelectedId(null);
        void refresh();
        return;
      }
      void refresh();
      if (!event.project_id || event.project_id === selectedId) void refreshOverview();
    };
    return () => socket.close();
  }, [refresh, refreshOverview, selectedId]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedId) ?? null,
    [projects, selectedId]
  );

  async function createAndStart(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const project = await api<Project>("/api/projects", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          repository_path: form.repository_path,
          privacy_level: "PRIVATE"
        })
      });
      await api(`/api/projects/${project.id}/goals`, {
        method: "POST",
        body: JSON.stringify({ prompt: form.goal })
      });
      await api(`/api/projects/${project.id}/plan`, { method: "POST" });
      await api(`/api/projects/${project.id}/start`, { method: "POST" });
      setForm({ name: "", repository_path: "", goal: "" });
      setSelectedId(project.id);
      await refresh();
      await refreshOverview();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project creation failed");
    } finally {
      setBusy(false);
    }
  }

  async function projectAction(action: "pause" | "resume") {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/api/projects/${selectedId}/${action}`, { method: "POST" });
      await refresh();
      await refreshOverview();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to ${action}`);
    } finally {
      setBusy(false);
    }
  }

  async function deleteProject(project: Project) {
    if (!window.confirm(`Delete project ${project.name} and all of its tasks? This cannot be undone.`)) return;
    setBusy(true);
    setError(null);
    try {
      await api<void>(`/api/projects/${project.id}`, { method: "DELETE" });
      const nextProject = projects.find((item) => item.id !== project.id) ?? null;
      setProjects((current) => current.filter((item) => item.id !== project.id));
      setSelectedId(nextProject?.id ?? null);
      setOverview(null);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to delete project");
    } finally {
      setBusy(false);
    }
  }

  async function taskAction(task: Task, action: "pause" | "resume" | "cancel") {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/tasks/${task.id}/${action}`, { method: "POST" });
      await Promise.all([refresh(), refreshOverview()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to ${action} task`);
    } finally {
      setBusy(false);
    }
  }

  async function deleteTask(task: Task) {
    if (!window.confirm(`Delete ${task.key} — ${task.title}? This cannot be undone.`)) return;
    setBusy(true);
    setError(null);
    try {
      await api<void>(`/api/tasks/${task.id}`, { method: "DELETE" });
      setOverview((current) => current ? {
        ...current,
        tasks: current.tasks.filter((item) => item.id !== task.id)
      } : current);
      await Promise.all([refresh(), refreshOverview()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to delete task");
    } finally {
      setBusy(false);
    }
  }

  async function saveOpenRouter(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/providers/openrouter", {
        method: "PUT",
        body: JSON.stringify({
          kind: "openai_compatible",
          enabled: openRouter.enabled,
          base_url: openRouter.base_url,
          api_key_env: "OPENROUTER_API_KEY",
          ...(openRouter.api_key ? { api_key: openRouter.api_key } : {}),
          billing_mode: "free",
          accepts_private_code: openRouter.accepts_private_code,
          timeout_seconds: 60
        })
      });
      setOpenRouter((current) => ({ ...current, api_key: "" }));
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save OpenRouter");
    } finally {
      setBusy(false);
    }
  }

  async function testProvider(name: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ available: boolean; detail: string }>(`/api/providers/${name}/test`, { method: "POST" });
      if (!result.available) throw new Error(`${name}: ${result.detail}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to test ${name}`);
    } finally {
      setBusy(false);
    }
  }

  async function discoverModels(provider: string) {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/models/discover?provider=${encodeURIComponent(provider)}`, { method: "POST" });
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to scan ${provider}`);
    } finally {
      setBusy(false);
    }
  }

  async function selectModel(role: string, modelId: string) {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/model-selection/${role}`, {
        method: "PUT",
        body: JSON.stringify({ model_id: modelId })
      });
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to select model");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="shell">
      <aside>
        <div className="brand"><span>A</span><div>AutoDev<small>Control room</small></div></div>
        <nav>
          <p>Projects</p>
          {projects.map((project) => (
            <button
              className={project.id === selectedId ? "selected" : ""}
              key={project.id}
              onClick={() => setSelectedId(project.id)}
            >
              <i className={statusTone(project.status)} />
              <span>{project.name}<small>{project.status.toLowerCase()}</small></span>
            </button>
          ))}
          {!projects.length && <div className="empty-small">No projects yet</div>}
        </nav>
        <div className="connection"><i className={connected ? "good" : "bad"} />{connected ? "Live" : "Reconnecting"}</div>
      </aside>

      <main>
        <header>
          <div><p className="eyebrow">AUTONOMOUS DELIVERY</p><h1>Engineering command center</h1></div>
          <button className="secondary" onClick={() => void refresh()}>Refresh data</button>
        </header>

        {error && <div className="error"><span>!</span>{error}<button onClick={() => setError(null)}>×</button></div>}

        <section className="metrics">
          <article><small>Projects</small><strong>{summary ? total(summary.projects) : "—"}</strong><p>{summary?.projects.IMPLEMENTING ?? 0} executing now</p></article>
          <article><small>Tasks</small><strong>{summary ? total(summary.tasks) : "—"}</strong><p>{summary?.tasks.COMPLETED ?? 0} completed</p></article>
          <article><small>QA findings</small><strong>{summary?.open_qa_findings ?? "—"}</strong><p>Open and actionable</p></article>
          <article><small>Deployments</small><strong>{summary?.active_deployments ?? "—"}</strong><p>Active pipelines</p></article>
        </section>

        <section className="workspace-grid">
          <article className="panel project-panel">
            <div className="panel-title">
              <div><p className="eyebrow">SELECTED PROJECT</p><h2>{selectedProject?.name ?? "No project selected"}</h2></div>
              {selectedProject && <span className={`badge ${statusTone(selectedProject.status)}`}>{selectedProject.status}</span>}
            </div>
            {selectedProject ? (
              <>
                <p className="repo">{selectedProject.repository_path}</p>
                <div className="actions">
                  {selectedProject.status === "PAUSED" ?
                    <button disabled={busy} onClick={() => void projectAction("resume")}>Resume project</button> :
                    <button disabled={busy || ["COMPLETED", "FAILED"].includes(selectedProject.status)} onClick={() => void projectAction("pause")}>Pause project</button>}
                  <button className="danger" disabled={busy} onClick={() => void deleteProject(selectedProject)}>Delete project</button>
                  <span>{selectedProject.privacy_level}</span>
                </div>
                <div className="task-list">
                  {overview?.tasks.map((task) => (
                    <div className="task" key={task.id}>
                      <div><b>{task.key}</b><span>{task.title}</span></div>
                      <div className="task-controls">
                        <div className="task-meta"><span>P{task.priority}</span><span>A{task.attempts}</span><em className={statusTone(task.status)}>{task.status}</em></div>
                        {task.status === "PAUSED" ?
                          <button type="button" className="task-button secondary" disabled={busy} onClick={() => void taskAction(task, "resume")}>Resume</button> :
                          pausableTaskStatuses.has(task.status) &&
                            <button type="button" className="task-button secondary" disabled={busy} onClick={() => void taskAction(task, "pause")}>Pause</button>}
                        {cancellableTaskStatuses.has(task.status) &&
                          <button type="button" className="task-button secondary" disabled={busy} onClick={() => void taskAction(task, "cancel")}>Cancel</button>}
                        <button
                          type="button"
                          className="task-button danger"
                          disabled={busy || activeTaskStatuses.has(task.status)}
                          title={activeTaskStatuses.has(task.status) ? "Stop the active task before deleting it" : `Delete ${task.key}`}
                          onClick={() => void deleteTask(task)}
                        >Delete</button>
                      </div>
                    </div>
                  ))}
                  {!overview?.tasks.length && <div className="empty">No planned tasks</div>}
                </div>
              </>
            ) : <div className="empty">Create a goal-driven project to start the orchestrator.</div>}
          </article>

          <article className="panel create-panel">
            <div className="panel-title"><div><p className="eyebrow">NEW RUN</p><h2>Start from a goal</h2></div><span className="step">01 → 04</span></div>
            <form onSubmit={(event) => void createAndStart(event)}>
              <label>Project name<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="Billing service" /></label>
              <label>Repository path<input required value={form.repository_path} onChange={(event) => setForm({ ...form, repository_path: event.target.value })} placeholder="G:\\projects\\billing" /></label>
              <label>Goal<textarea required value={form.goal} onChange={(event) => setForm({ ...form, goal: event.target.value })} placeholder="Add idempotent invoice processing with tests…" /></label>
              <button disabled={busy}>{busy ? "Starting…" : "Plan and start"}</button>
            </form>
          </article>
        </section>

        <section className="lower-grid">
          <article className="panel">
            <div className="panel-title"><div><p className="eyebrow">ROUTING</p><h2>Model performance</h2></div></div>
            <div className="model-table">
              <div className="table-head"><span>Provider / model</span><span>Health</span><span>Success</span><span>Latency</span></div>
              {modelStats.map((model) => (
                <div className="model-row" key={`${model.provider}/${model.model}`}>
                  <span><b>{model.model}</b><small>{model.provider} · {model.calls} calls</small></span>
                  <em className={statusTone(model.health)}>{model.health}</em>
                  <span>{Math.round(model.success_rate * 100)}%</span>
                  <span>{model.average_latency_seconds.toFixed(1)}s</span>
                </div>
              ))}
              {!modelStats.length && <div className="empty">Usage appears after the first routed task.</div>}
            </div>
          </article>

          <article className="panel event-panel">
            <div className="panel-title"><div><p className="eyebrow">EVENT STREAM</p><h2>Live activity</h2></div><span className="pulse" /></div>
            <div className="event-list">
              {events.map((event) => (
                <div key={event.id}><i /><span><b>{event.name}</b><small>{new Date(event.occurred_at).toLocaleTimeString()}</small></span></div>
              ))}
              {!events.length && overview?.events.slice(0, 8).map((event, index) => (
                <div key={`${event.event}-${index}`}><i /><span><b>{event.event}</b><small>{new Date(event.created_at).toLocaleTimeString()}</small></span></div>
              ))}
              {!events.length && !overview?.events.length && <div className="empty">Waiting for orchestrator events…</div>}
            </div>
          </article>
        </section>

        <section className="settings-grid" id="model-settings">
          <article className="panel provider-settings">
            <div className="panel-title">
              <div><p className="eyebrow">PROVIDER SETTINGS</p><h2>OpenRouter API</h2></div>
              <span className={`badge ${providers.find((item) => item.name === "openrouter")?.credential_configured ? "good" : "warn"}`}>
                {providers.find((item) => item.name === "openrouter")?.credential_configured ? "KEY SAVED" : "NO KEY"}
              </span>
            </div>
            <form onSubmit={(event) => void saveOpenRouter(event)}>
              <label className="toggle-row">
                <input type="checkbox" checked={openRouter.enabled} onChange={(event) => setOpenRouter({ ...openRouter, enabled: event.target.checked })} />
                Enable OpenRouter
              </label>
              <label>Base URL<input value={openRouter.base_url} onChange={(event) => setOpenRouter({ ...openRouter, base_url: event.target.value })} /></label>
              <label>API key<input type="password" autoComplete="off" value={openRouter.api_key} onChange={(event) => setOpenRouter({ ...openRouter, api_key: event.target.value })} placeholder="Stored encrypted; never returned by API" /></label>
              <label className="toggle-row">
                <input type="checkbox" checked={openRouter.accepts_private_code} onChange={(event) => setOpenRouter({ ...openRouter, accepts_private_code: event.target.checked })} />
                Allow private repository context
              </label>
              <div className="actions">
                <button disabled={busy}>Save settings</button>
                <button type="button" className="secondary" disabled={busy || !openRouter.enabled} onClick={() => void testProvider("openrouter")}>Test</button>
                <button type="button" className="secondary" disabled={busy || !openRouter.enabled} onClick={() => void discoverModels("openrouter")}>Load models</button>
              </div>
            </form>
          </article>

          <article className="panel local-settings">
            <div className="panel-title">
              <div><p className="eyebrow">LOCAL RUNTIME</p><h2>Choose local model</h2></div>
              <button className="secondary" disabled={busy} onClick={() => void discoverModels("ollama")}>Scan Ollama</button>
            </div>
            <p className="hint">The selected implementation model analyzes the task locally; Codex remains the isolated file and Git executor.</p>
            <div className="local-models">
              {configuredModels.filter((model) => model.provider === "ollama" && model.roles.includes("implementation")).map((model) => (
                <div className="local-model" key={model.id}>
                  <div><b>{model.display_name}</b><small>{model.installed ? "Installed on this machine" : "Not installed"}</small></div>
                  {model.selected_for.includes("implementation") ?
                    <span className="badge good">SELECTED</span> :
                    <button disabled={busy || !model.installed || !model.enabled} onClick={() => void selectModel("implementation", model.id)}>Use model</button>}
                </div>
              ))}
              {!configuredModels.some((model) => model.provider === "ollama" && model.roles.includes("implementation")) && <div className="empty">Scan Ollama to load installed models.</div>}
            </div>
          </article>
        </section>
      </main>
    </div>
  );
}
