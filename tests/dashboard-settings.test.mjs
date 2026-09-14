import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import test from 'node:test';
import { injectSettings, settingsRoute } from '../dashboard/settings.mjs';

const tempDirectory = mkdtempSync(join(tmpdir(), 'agentmemory-settings-'));
const envPath = join(tempDirectory, '.env');
writeFileSync(envPath, 'UNRELATED=value\n');
const html = injectSettings('<html><body></body></html>', 'nonce-for-test');
const requestToken = html.match(/'X-Settings-Token':'([^']+)'/)[1];

async function request(method, body, options = {}) {
  const req = Readable.from([JSON.stringify(body ?? {})]);
  Object.assign(req, {
    url: '/local-settings/openrouter',
    method,
    headers: {
      host: 'localhost:3113',
      origin: options.origin ?? 'http://localhost:3113',
      'x-settings-token': requestToken,
    },
  });
  let statusCode;
  let responseBody;
  const res = {
    writeHead(code) { statusCode = code; },
    end(value) { responseBody = JSON.parse(value); },
  };
  await settingsRoute(req, res, {
    path: envPath,
    fetch: async () => ({ ok: options.openRouterStatus !== 401, status: options.openRouterStatus ?? 200 }),
    restart: options.restart ?? (() => {}),
  });
  return { statusCode, responseBody };
}

test('rejects malformed and cross-origin requests', async () => {
  assert.equal((await request('POST', { key: 'bad' })).statusCode, 400);
  assert.equal((await request('POST', { key: 'bad' }, { origin: 'https://example.invalid' })).statusCode, 403);
});

test('does not save a key rejected by OpenRouter', async () => {
  const key = `sk-or-v1-${'a'.repeat(32)}`;
  assert.equal((await request('POST', { key }, { openRouterStatus: 401 })).statusCode, 400);
  assert.doesNotMatch(readFileSync(envPath, 'utf8'), new RegExp(key));
});

test('saves only the free route and never returns the key', async () => {
  const key = `sk-or-v1-${'b'.repeat(32)}`;
  let restarts = 0;
  assert.equal((await request('POST', { key }, { restart: () => restarts++ })).statusCode, 200);
  assert.equal(restarts, 1);
  const env = readFileSync(envPath, 'utf8');
  assert.match(env, /UNRELATED=value/);
  assert.match(env, /OPENROUTER_MODEL=openrouter\/free/);
  assert.match(env, /GRAPH_EXTRACTION_ENABLED=true/);
  const status = await request('GET');
  assert.equal(status.responseBody.configured, true);
  assert.doesNotMatch(JSON.stringify(status), new RegExp(key));
});
