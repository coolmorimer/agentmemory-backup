import { spawn } from 'node:child_process';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { createInterface } from 'node:readline';

const repositoryRoot = process.argv[2];
const pluginId = process.argv[3] || 'agentmemory@agentmemory-backup';
if (!repositoryRoot) throw new Error('Repository root is required.');
const [pluginName, marketplaceName] = pluginId.split('@');
if (!pluginName || !marketplaceName) throw new Error('Plugin id must include its marketplace.');
const expectedCacheRoot = join(homedir(), '.codex', 'plugins', 'cache', marketplaceName, pluginName).toLowerCase();

const child = spawn('codex', ['app-server', '--stdio'], {
  stdio: ['pipe', 'pipe', 'inherit'],
  windowsHide: true,
});
const lines = createInterface({ input: child.stdout });
const pending = new Map();
let nextId = 1;
lines.on('line', line => {
  let message;
  try { message = JSON.parse(line); } catch { return; }
  const waiter = pending.get(message.id);
  if (!waiter) return;
  pending.delete(message.id);
  if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
  else waiter.resolve(message.result);
});

function call(method, params) {
  const id = nextId++;
  child.stdin.write(JSON.stringify({ id, method, params }) + '\n');
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    setTimeout(() => {
      if (pending.delete(id)) reject(new Error(`Timed out calling ${method}.`));
    }, 30000).unref();
  });
}

try {
  await call('initialize', {
    clientInfo: { name: 'agentmemory-installer', version: '1.0' },
    capabilities: { experimentalApi: true },
  });
  child.stdin.write(JSON.stringify({ method: 'initialized' }) + '\n');
  const listed = await call('hooks/list', { cwds: [repositoryRoot] });
  const hooks = listed.data.flatMap(item => item.hooks).filter(hook =>
    hook.pluginId === pluginId &&
    hook.source === 'plugin' &&
    hook.sourcePath.toLowerCase().startsWith(expectedCacheRoot)
  );
  if (hooks.length !== 6) throw new Error(`Expected 6 AgentMemory hooks, found ${hooks.length}.`);
  const edits = hooks.map(hook => ({
    keyPath: `hooks.state.${JSON.stringify(hook.key)}.trusted_hash`,
    value: hook.currentHash,
    mergeStrategy: 'replace',
  }));
  await call('config/batchWrite', { edits, reloadUserConfig: true });
  const verified = await call('hooks/list', { cwds: [repositoryRoot] });
  const trusted = verified.data.flatMap(item => item.hooks).filter(hook =>
    hook.pluginId === pluginId && hook.trustStatus === 'trusted'
  );
  if (trusted.length !== 6) throw new Error(`Only ${trusted.length} of 6 hooks are trusted.`);
  console.log('All 6 AgentMemory hooks are trusted.');
} finally {
  child.kill();
}
