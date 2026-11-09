import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadSnapshot } from '../src/api.ts';
import { ApiError, requestApi } from '../src/transport.ts';

const response = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const absent = () => response({ ok: false, error: 'endpoint' }, 404);

test('demo requires an explicit choice and makes no requests', async () => {
  const value = await loadSnapshot({ demo: true, fetcher: () => { throw new Error('unexpected request'); } });
  assert.equal(value.source, 'mock');
});

for (const status of [401, 403]) {
  test(`HTTP ${status} never becomes a demo`, async () => {
    await assert.rejects(loadSnapshot({ fetcher: async () => response({}, status) }), error => error instanceof ApiError && error.code === 'auth');
  });
}

test('unavailable API never becomes a demo', async () => {
  await assert.rejects(loadSnapshot({ fetcher: async () => absent() }), error => error.code === 'unavailable');
});

test('missing F317 endpoint preserves F314 readings', async () => {
  const value = await loadSnapshot({ fetcher: async path => {
    if (path === '/api/v1/status') return response({ ok: true, health: 'degraded', uptime_seconds: 12, memory: { available_kb: 22944 } });
    if (path === '/api/v1/firmware') return response({ ok: true, version: 'F314-test', kernel: 'kernel-test' });
    if (path === '/api/v1/capabilities') return response({ ok: true, items: [{ id: 'dfs', title: 'Radar' }] });
    return absent();
  }});
  assert.equal(value.source, 'router');
  assert.equal(value.version, 'F314-test');
  assert.equal(value.health, 'degraded');
  assert.equal(value.memoryFreeMiB, 22944 / 1024);
  assert.deepEqual(value.capabilities, ['Radar']);
  assert.equal(value.optimization.automaticApply, false);
});

test('auth failure on an optional endpoint is still an auth failure', async () => {
  await assert.rejects(loadSnapshot({ fetcher: async path => path === '/api/v1/status'
    ? response({ ok: true, health: 'ready' }) : response({}, 403) }), error => error.code === 'auth');
});

test('HTTP success with ok:false is rejected', async () => {
  await assert.rejects(requestApi('/api/v1/status', {}, async () => response({ ok: false, error: 'not-ready' })), error => error.code === 'not-ready');
});

test('lost POST response is ambiguous and is not retried', async () => {
  let calls = 0;
  await assert.rejects(requestApi('/api/v1/config/apply', { method: 'POST' }, async () => {
    calls++;
    throw new Error('connection lost');
  }), error => error.ambiguous === true);
  assert.equal(calls, 1);
});

test('external paths are refused before a request', async () => {
  let calls = 0;
  await assert.rejects(requestApi('https://example.com', {}, async () => { calls++; return response({}); }), error => error.code === 'path');
  assert.equal(calls, 0);
});

test('requests retain session and forbid cached or redirected responses', async () => {
  await requestApi('/api/v1/status', {}, async (_, init) => {
    assert.equal(init.credentials, 'same-origin');
    assert.equal(init.cache, 'no-store');
    assert.equal(init.redirect, 'error');
    return response({ ok: true });
  });
});
