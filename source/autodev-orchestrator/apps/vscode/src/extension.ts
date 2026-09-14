import * as vscode from "vscode";

type Project = {
  id: string;
  name: string;
  repository_path: string;
  privacy_level: string;
  status: string;
};

type Task = {
  id: string;
  project_id: string;
  key: string;
  title: string;
  status: string;
};

type Provider = {
  name: string;
  enabled: boolean;
  billing_mode: string;
  credential_configured: boolean;
};

type Model = {
  id: string;
  provider: string;
  display_name: string;
  enabled: boolean;
  installed: boolean;
  roles: string[];
  selected_for: string[];
};

type DashboardSummary = {
  projects: Record<string, number>;
  tasks: Record<string, number>;
  open_qa_findings: number;
  active_deployments: number;
};

class ApiClient {
  private get baseUrl(): string {
    return vscode.workspace.getConfiguration("autodev").get<string>("apiUrl")!.replace(/\/$/, "");
  }

  async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers }
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText })) as { detail?: string };
      throw new Error(body.detail ?? `HTTP ${response.status}`);
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }

  health(): Promise<{ status: string }> { return this.request("/health"); }
  projects(): Promise<Project[]> { return this.request("/api/projects"); }
  tasks(projectId: string): Promise<Task[]> { return this.request(`/api/projects/${projectId}/tasks`); }
  providers(): Promise<Provider[]> { return this.request("/api/providers"); }
  models(): Promise<Model[]> { return this.request("/api/models"); }
  summary(): Promise<DashboardSummary> { return this.request("/api/dashboard/summary"); }
}

class SimpleItem extends vscode.TreeItem {
  constructor(label: string, description?: string, collapsible = vscode.TreeItemCollapsibleState.None) {
    super(label, collapsible);
    this.description = description;
  }
}

class ProjectsProvider implements vscode.TreeDataProvider<SimpleItem> {
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;

  constructor(private readonly api: ApiClient) {}
  refresh(): void { this.emitter.fire(); }
  getTreeItem(item: SimpleItem): vscode.TreeItem { return item; }

  async getChildren(): Promise<SimpleItem[]> {
    try {
      return (await this.api.projects()).map((project) => {
        const item = new SimpleItem(project.name, project.status);
        item.tooltip = `${project.repository_path}\n${project.privacy_level}`;
        item.iconPath = new vscode.ThemeIcon(project.status === "COMPLETED" ? "pass-filled" : "run-all");
        item.command = { command: "autodev.openControlRoom", title: "Open", arguments: [project.id] };
        return item;
      });
    } catch (error) {
      return [new SimpleItem("API unavailable", message(error))];
    }
  }
}

class ModelsProvider implements vscode.TreeDataProvider<SimpleItem> {
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;

  constructor(private readonly api: ApiClient) {}
  refresh(): void { this.emitter.fire(); }
  getTreeItem(item: SimpleItem): vscode.TreeItem { return item; }

  async getChildren(): Promise<SimpleItem[]> {
    try {
      const [providers, models] = await Promise.all([this.api.providers(), this.api.models()]);
      const providerItems = providers.map((provider) => {
        const state = provider.enabled ? "enabled" : "disabled";
        const key = provider.credential_configured ? " · key saved" : "";
        const item = new SimpleItem(provider.name, `${state}${key}`);
        item.iconPath = new vscode.ThemeIcon(provider.enabled ? "server-process" : "circle-slash");
        return item;
      });
      const modelItems = models
        .map((model) => {
          const selected = model.selected_for.length ? ` · ${model.selected_for.join(", ")}` : "";
          const availability = model.provider === "ollama"
            ? (model.installed ? "installed" : "missing")
            : (model.enabled ? "available" : "disabled");
          const item = new SimpleItem(
            `${model.provider} / ${model.display_name}`,
            `${availability}${selected}`
          );
          item.iconPath = new vscode.ThemeIcon(model.selected_for.length ? "check" : "symbol-variable");
          return item;
        });
      return [...providerItems, ...modelItems];
    } catch (error) {
      return [new SimpleItem("API unavailable", message(error))];
    }
  }
}

class ControlRoomProvider implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  constructor(private readonly api: ApiClient) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = { enableScripts: true };
    view.webview.onDidReceiveMessage((event: { command?: string }) => {
      if (event.command) void vscode.commands.executeCommand(`autodev.${event.command}`);
    });
    void this.refresh();
  }

  async refresh(): Promise<void> {
    if (!this.view) return;
    try {
      const [summary, providers, models] = await Promise.all([
        this.api.summary(), this.api.providers(), this.api.models()
      ]);
      const selected = models.find((model) => model.selected_for.includes("implementation"));
      const ollama = providers.find((provider) => provider.name === "ollama");
      const openrouter = providers.find((provider) => provider.name === "openrouter");
      this.view.webview.html = html({
        projectCount: total(summary.projects),
        taskCount: total(summary.tasks),
        ollama: ollama?.enabled ? "enabled" : "disabled",
        openrouter: openrouter?.credential_configured ? "key saved" : "not configured",
        selectedModel: selected?.display_name ?? "automatic (Codex)",
        error: undefined
      });
    } catch (error) {
      this.view.webview.html = html({
        projectCount: 0, taskCount: 0, ollama: "offline", openrouter: "unknown",
        selectedModel: "unavailable", error: message(error)
      });
    }
  }
}

let workerTerminal: vscode.Terminal | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const api = new ApiClient();
  const projects = new ProjectsProvider(api);
  const models = new ModelsProvider(api);
  const control = new ControlRoomProvider(api);
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  status.command = "autodev.openControlRoom";
  status.show();

  const refresh = async () => {
    projects.refresh();
    models.refresh();
    await control.refresh();
    try {
      await api.health();
      status.text = "$(pulse) AutoDev ready";
      status.tooltip = "Open AutoDev Control Room";
      status.backgroundColor = undefined;
    } catch (error) {
      status.text = "$(warning) AutoDev offline";
      status.tooltip = message(error);
      status.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    }
  };

  context.subscriptions.push(
    status,
    vscode.window.registerTreeDataProvider("autodev.projects", projects),
    vscode.window.registerTreeDataProvider("autodev.models", models),
    vscode.window.registerWebviewViewProvider("autodev.control", control),
    vscode.commands.registerCommand("autodev.refresh", refresh),
    vscode.commands.registerCommand("autodev.openControlRoom", async () => {
      const url = vscode.workspace.getConfiguration("autodev").get<string>("dashboardUrl")!;
      await vscode.env.openExternal(vscode.Uri.parse(url));
    }),
    vscode.commands.registerCommand("autodev.newGoal", () => createGoal(api, refresh)),
    vscode.commands.registerCommand("autodev.deleteProject", () => deleteProject(api, refresh)),
    vscode.commands.registerCommand("autodev.pauseTask", () => pauseTask(api, refresh)),
    vscode.commands.registerCommand("autodev.resumeTask", () => resumeTask(api, refresh)),
    vscode.commands.registerCommand("autodev.cancelTask", () => cancelTask(api, refresh)),
    vscode.commands.registerCommand("autodev.deleteTask", () => deleteTask(api, refresh)),
    vscode.commands.registerCommand("autodev.configureOpenRouter", () => configureOpenRouter(context, api, refresh)),
    vscode.commands.registerCommand("autodev.discoverModels", () => discoverModels(api, refresh)),
    vscode.commands.registerCommand("autodev.discoverOllamaModels", () => discoverModels(api, refresh, "ollama")),
    vscode.commands.registerCommand("autodev.discoverOpenRouterModels", () => discoverModels(api, refresh, "openrouter")),
    vscode.commands.registerCommand("autodev.selectLocalModel", () => selectLocalModel(api, refresh)),
    vscode.commands.registerCommand("autodev.startWorker", startWorker),
    vscode.commands.registerCommand("autodev.stopWorker", stopWorker),
    vscode.commands.registerCommand("autodev.doctor", runDoctor)
  );

  const seconds = vscode.workspace.getConfiguration("autodev").get<number>("refreshSeconds") ?? 5;
  const timer = setInterval(() => void refresh(), seconds * 1000);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });
  void refresh();
}

async function createGoal(api: ApiClient, refresh: () => Promise<void>): Promise<void> {
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? "";
  const name = await vscode.window.showInputBox({ prompt: "Project name", value: folder.split(/[\\/]/).pop() });
  if (!name) return;
  const repositoryPath = await vscode.window.showInputBox({ prompt: "Repository path", value: folder });
  if (!repositoryPath) return;
  const goal = await vscode.window.showInputBox({ prompt: "What should AutoDev build?", ignoreFocusOut: true });
  if (!goal) return;
  try {
    const project = await api.request<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, repository_path: repositoryPath, privacy_level: "PRIVATE" })
    });
    await api.request(`/api/projects/${project.id}/goals`, { method: "POST", body: JSON.stringify({ prompt: goal }) });
    await api.request(`/api/projects/${project.id}/plan`, { method: "POST" });
    await api.request(`/api/projects/${project.id}/start`, { method: "POST" });
    await refresh();
    void vscode.window.showInformationMessage(`AutoDev started ${name}`);
  } catch (error) {
    void vscode.window.showErrorMessage(`AutoDev: ${message(error)}`);
  }
}

async function deleteProject(api: ApiClient, refresh: () => Promise<void>): Promise<void> {
  try {
    const projects = await api.projects();
    if (!projects.length) {
      void vscode.window.showInformationMessage("AutoDev: no projects to delete.");
      return;
    }
    const picked = await vscode.window.showQuickPick(
      projects.map((project) => ({
        label: project.name,
        description: project.status,
        detail: project.repository_path,
        project
      })),
      { title: "Delete an AutoDev project", matchOnDescription: true, matchOnDetail: true }
    );
    if (!picked) return;
    const confirmation = await vscode.window.showWarningMessage(
      `Permanently delete ${picked.project.name} and all of its tasks?`,
      { modal: true, detail: "Runtime records will be removed. Audit history is retained." },
      "Delete project"
    );
    if (confirmation !== "Delete project") return;
    await api.request<void>(`/api/projects/${picked.project.id}`, { method: "DELETE" });
    await refresh();
    void vscode.window.showInformationMessage(`AutoDev deleted ${picked.project.name}.`);
  } catch (error) {
    void vscode.window.showErrorMessage(`Project deletion: ${message(error)}`);
  }
}

async function pickTask(
  api: ApiClient,
  title: string,
  allowedStatuses?: ReadonlySet<string>
): Promise<Task | undefined> {
  const projects = await api.projects();
  const taskGroups = await Promise.all(
    projects.map(async (project) => ({ project, tasks: await api.tasks(project.id) }))
  );
  const choices = taskGroups.flatMap(({ project, tasks }) => tasks
    .filter((task) => !allowedStatuses || allowedStatuses.has(task.status))
    .map((task) => ({
      label: `${task.key} — ${task.title}`,
      description: `${project.name} · ${task.status}`,
      task
    })));
  if (!choices.length) {
    void vscode.window.showInformationMessage("AutoDev: no matching tasks.");
    return undefined;
  }
  return (await vscode.window.showQuickPick(choices, { title, matchOnDescription: true }))?.task;
}

async function cancelTask(api: ApiClient, refresh: () => Promise<void>): Promise<void> {
  const cancellableStatuses = new Set(["RUNNING", "TESTING", "REVIEWING"]);
  try {
    const task = await pickTask(api, "Stop an active AutoDev task", cancellableStatuses);
    if (!task) return;
    const confirmation = await vscode.window.showWarningMessage(
      `Stop ${task.key} — ${task.title}?`,
      { modal: true },
      "Stop task"
    );
    if (confirmation !== "Stop task") return;
    await api.request(`/api/tasks/${task.id}/cancel`, { method: "POST" });
    await refresh();
    void vscode.window.showInformationMessage(`AutoDev stopped ${task.key}.`);
  } catch (error) {
    void vscode.window.showErrorMessage(`Task cancellation: ${message(error)}`);
  }
}

async function pauseTask(api: ApiClient, refresh: () => Promise<void>): Promise<void> {
  const pausableStatuses = new Set([
    "DRAFT", "READY", "WAITING_DEPENDENCY", "WAITING_PROVIDER", "RUNNING", "TESTING",
    "REVIEWING", "FIX_REQUIRED", "BLOCKED"
  ]);
  try {
    const task = await pickTask(api, "Pause one AutoDev task", pausableStatuses);
    if (!task) return;
    await api.request(`/api/tasks/${task.id}/pause`, { method: "POST" });
    await refresh();
    void vscode.window.showInformationMessage(
      `AutoDev paused ${task.key}; other tasks in the project continue.`
    );
  } catch (error) {
    void vscode.window.showErrorMessage(`Task pause: ${message(error)}`);
  }
}

async function resumeTask(api: ApiClient, refresh: () => Promise<void>): Promise<void> {
  try {
    const task = await pickTask(api, "Resume one AutoDev task", new Set(["PAUSED"]));
    if (!task) return;
    await api.request(`/api/tasks/${task.id}/resume`, { method: "POST" });
    await refresh();
    void vscode.window.showInformationMessage(`AutoDev resumed ${task.key}.`);
  } catch (error) {
    void vscode.window.showErrorMessage(`Task resume: ${message(error)}`);
  }
}

async function deleteTask(api: ApiClient, refresh: () => Promise<void>): Promise<void> {
  const activeStatuses = new Set(["RUNNING", "TESTING", "REVIEWING", "APPROVED"]);
  try {
    const task = await pickTask(api, "Delete an AutoDev task");
    if (!task) return;
    if (activeStatuses.has(task.status)) {
      void vscode.window.showWarningMessage(
        `${task.key} is active. Stop it and wait for the worker before deleting it.`
      );
      return;
    }
    const confirmation = await vscode.window.showWarningMessage(
      `Permanently delete ${task.key} — ${task.title}?`,
      { modal: true, detail: "Task runtime records will be removed. Audit history is retained." },
      "Delete task"
    );
    if (confirmation !== "Delete task") return;
    await api.request<void>(`/api/tasks/${task.id}`, { method: "DELETE" });
    await refresh();
    void vscode.window.showInformationMessage(`AutoDev deleted ${task.key}.`);
  } catch (error) {
    void vscode.window.showErrorMessage(`Task deletion: ${message(error)}`);
  }
}

async function configureOpenRouter(context: vscode.ExtensionContext, api: ApiClient, refresh: () => Promise<void>): Promise<void> {
  const apiKey = await vscode.window.showInputBox({
    title: "OpenRouter API key", prompt: "The key is encrypted by AutoDev and never returned by its API.",
    password: true, ignoreFocusOut: true
  });
  if (!apiKey) return;
  const privacy = await vscode.window.showQuickPick(
    [{ label: "Public code only", value: false }, { label: "Allow private code", value: true }],
    { title: "OpenRouter privacy policy" }
  );
  if (!privacy) return;
  try {
    await context.secrets.store("openrouterApiKey", apiKey);
    await api.request("/api/providers/openrouter", {
      method: "PUT",
      body: JSON.stringify({
        kind: "openai_compatible", enabled: true, base_url: "https://openrouter.ai/api/v1",
        api_key_env: "OPENROUTER_API_KEY", api_key: apiKey, billing_mode: "free",
        accepts_private_code: privacy.value, timeout_seconds: 60
      })
    });
    await refresh();
    const health = await api.request<{ available: boolean; detail?: string }>(
      "/api/providers/openrouter/test", { method: "POST" }
    );
    if (!health.available) {
      void vscode.window.showWarningMessage(
        `OpenRouter settings saved, but the connection test failed: ${health.detail ?? "unavailable"}`
      );
      return;
    }
    const discovered = await api.request<{ models: string[] }>(
      "/api/models/discover?provider=openrouter", { method: "POST" }
    );
    await refresh();
    void vscode.window.showInformationMessage(
      `OpenRouter configured and verified; ${discovered.models.length} model(s) loaded.`
    );
  } catch (error) {
    void vscode.window.showErrorMessage(`OpenRouter: ${message(error)}`);
  }
}

async function discoverModels(
  api: ApiClient,
  refresh: () => Promise<void>,
  requestedProvider?: "ollama" | "openrouter"
): Promise<void> {
  try {
    const provider = requestedProvider ?? await vscode.window.showQuickPick(
      [
        { label: "Ollama", value: "ollama" as const, description: "Local installed models" },
        { label: "OpenRouter", value: "openrouter" as const, description: "Models available to your key" }
      ],
      { title: "Refresh model catalog" }
    ).then((picked) => picked?.value);
    if (!provider) return;
    const result = await api.request<{ models: string[] }>(
      `/api/models/discover?provider=${provider}`, { method: "POST" }
    );
    await refresh();
    void vscode.window.showInformationMessage(`Found ${result.models.length} ${provider} model(s).`);
  } catch (error) {
    void vscode.window.showErrorMessage(`Model discovery: ${message(error)}`);
  }
}

async function selectLocalModel(api: ApiClient, refresh: () => Promise<void>): Promise<void> {
  try {
    const models = (await api.models()).filter(
      (model) => model.provider === "ollama" && model.installed && model.enabled && model.roles.includes("implementation")
    );
    const picked = await vscode.window.showQuickPick(
      models.map((model) => ({ label: model.display_name, description: model.id, model })),
      { title: "Local implementation advisor" }
    );
    if (!picked) return;
    await api.request("/api/model-selection/implementation", {
      method: "PUT", body: JSON.stringify({ model_id: picked.model.id })
    });
    await refresh();
    void vscode.window.showInformationMessage(`AutoDev will use ${picked.label}.`);
  } catch (error) {
    void vscode.window.showErrorMessage(`Model selection: ${message(error)}`);
  }
}

function startWorker(): void {
  if (workerTerminal) { workerTerminal.show(); return; }
  const command = vscode.workspace.getConfiguration("autodev").get<string>("workerCommand")!;
  workerTerminal = vscode.window.createTerminal({
    name: "AutoDev Worker",
    cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
  });
  workerTerminal.sendText(command, true);
  workerTerminal.show();
}

function stopWorker(): void {
  workerTerminal?.dispose();
  workerTerminal = undefined;
}

function runDoctor(): void {
  const terminal = vscode.window.createTerminal({
    name: "AutoDev Doctor",
    cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
  });
  terminal.sendText("uv run autodev doctor --verbose", true);
  terminal.show();
}

function total(values: Record<string, number>): number {
  return Object.values(values).reduce((sum, value) => sum + value, 0);
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function html(state: {
  projectCount: number; taskCount: number; ollama: string; openrouter: string;
  selectedModel: string; error?: string;
}): string {
  const error = state.error ? `<p class="error">${escapeHtml(state.error)}</p>` : "";
  return `<!doctype html><html><head><meta charset="UTF-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline';"><style>
    body{font:12px var(--vscode-font-family);padding:10px;color:var(--vscode-foreground)}
    .hero{font-size:18px;font-weight:700;margin:2px 0 12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:7px}
    .card{padding:10px;border:1px solid var(--vscode-widget-border);border-radius:7px;background:var(--vscode-sideBar-background)}
    .card b{display:block;font-size:16px}.status{margin:12px 0;line-height:1.6}.status span{color:var(--vscode-descriptionForeground)}
    button{width:100%;margin:4px 0;padding:7px;border:0;border-radius:4px;color:var(--vscode-button-foreground);background:var(--vscode-button-background)}
    button.secondary{background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground)}.error{color:var(--vscode-errorForeground)}
  </style></head><body><div class="hero">AutoDev Control Room</div>${error}<div class="grid"><div class="card"><b>${state.projectCount}</b>projects</div><div class="card"><b>${state.taskCount}</b>tasks</div></div>
  <div class="status"><div><span>Ollama:</span> ${escapeHtml(state.ollama)}</div><div><span>OpenRouter:</span> ${escapeHtml(state.openrouter)}</div><div><span>Model:</span> ${escapeHtml(state.selectedModel)}</div></div>
  <button data-command="newGoal">Create and start goal</button><button data-command="deleteProject">Delete project</button><button data-command="pauseTask">Pause one task</button><button data-command="resumeTask">Resume paused task</button><button data-command="cancelTask">Cancel active task</button><button data-command="deleteTask">Delete task</button><button data-command="selectLocalModel">Select local model</button><button data-command="discoverOllamaModels">Scan Ollama models</button><button data-command="configureOpenRouter">Configure OpenRouter</button><button data-command="discoverOpenRouterModels">Refresh OpenRouter models</button><button data-command="startWorker">Start worker</button><button class="secondary" data-command="openControlRoom">Open full dashboard</button>
  <script>const vscode=acquireVsCodeApi();document.querySelectorAll('button').forEach(button=>button.addEventListener('click',()=>vscode.postMessage({command:button.dataset.command})));</script></body></html>`;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]!);
}

export function deactivate(): void {
  workerTerminal?.dispose();
}
