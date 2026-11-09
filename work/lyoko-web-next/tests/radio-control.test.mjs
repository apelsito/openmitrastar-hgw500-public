import { test } from 'node:test';
import assert from 'node:assert/strict';
import { RadioControl, parseContract } from '../src/radio-control.ts';

const ID = 'a'.repeat(64);
const CSRF = 'b'.repeat(64);
const json = value => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });

function harness() {
  const h = { current: { ssid: 'Original', channel: 36, bandwidth: '80', wmm: true }, pending: null, apply: true,
    csrf: CSRF, writes: [], channelWritable: false, dfsReady: false, loseApply: false, wrongReadback: false };
  h.contract = band => ({ ok: true, schema: 'lyoko.radio.contract/v1', id: band, settings: {
    ok: true, schema: 'lyoko.radio.settings/v2', id: band, settings: [
      { id: 'ssid', label: 'Nombre', type: 'string', current: h.current.ssid, allowed_values: { min_length: 1, max_length: 32 }, writable: true },
      { id: 'wmm', label: 'WMM', type: 'boolean', current: h.current.wmm, allowed_values: [false, true], writable: true },
      { id: 'channel', label: 'Canal', type: 'enum', current: h.current.channel, allowed_values: [36, 44, 52], writable: h.channelWritable, dfs_backend_ready: h.dfsReady },
      { id: 'bandwidth', label: 'Ancho', type: 'enum', current: '80', allowed_values: [20, 40, 80], writable: false },
      { id: 'dtim_period', label: 'DTIM', type: 'integer', current: 3, allowed_values: { min: 1, max: 15 }, writable: true }
    ]
  }});
  h.fetcher = async (path, init = {}) => {
    if (init.method !== 'POST') {
      if (path === '/api/v1/status') return json({ ok: true, schema: 'lyoko.api.status/v1', config_apply_enabled: h.apply, csrf: h.csrf });
      if (path === '/api/v1/config/status') return json(h.pending
        ? { ok: true, schema: 'lyoko.config.status/v2', pending: true, ...h.pending }
        : { ok: true, schema: 'lyoko.config.status/v2', pending: false, phase: 'none' });
      if (path.endsWith('?view=contract')) return json(h.contract(path.includes('/5g') ? '5g' : '2g'));
      if (/\/radios\/(2g|5g)$/.test(path)) return json({ ok: true, ...h.current, ...(h.wrongReadback ? { ssid: 'Unexpected' } : {}) });
      throw new Error(`unexpected GET ${path}`);
    }
    const body = new URLSearchParams(init.body);
    h.writes.push({ path, body: Object.fromEntries(body), headers: init.headers });
    if (path.endsWith('/stage')) {
      const after = Object.fromEntries(body);
      const before = Object.fromEntries(Object.keys(after).map(key => [key, String(h.current[key])]));
      h.pending = { transaction_id: ID, phase: 'staged', owned_by_session: true, band: path.includes('/5g') ? '5g' : '2g', snapshot: { before, after } };
      return json({ ok: true, schema: 'lyoko.config.stage/v2', transaction_id: ID, band: h.pending.band, applied: false, snapshot: h.pending.snapshot });
    }
    if (path.endsWith('/plan')) return json({ ok: true, apply_allowed: false, changes: Object.fromEntries(body) });
    if (path.endsWith('/apply')) {
      Object.assign(h.current, h.pending.snapshot.after);
      h.pending.phase = 'applied';
      if (h.loseApply) throw new Error('lost response after apply');
      return json({ ok: true, transaction_id: ID, applied: true, verified: true, confirmation_required: true });
    }
    if (path.endsWith('/commit')) { h.pending = null; return json({ ok: true, transaction_id: ID, committed: true, persistence: 'volatile' }); }
    if (path.endsWith('/rollback')) {
      Object.assign(h.current, h.pending.snapshot.before); h.pending = null;
      return json({ ok: true, transaction_id: ID, rolled_back: true, verified: true });
    }
    throw new Error(`unexpected POST ${path}`);
  };
  h.client = new RadioControl(h.fetcher);
  return h;
}

test('stage/apply/readback/commit follows the F314 body and header contract', async () => {
  const h = harness();
  await h.client.prepare('5g', { ssid: 'NewName' }, { ssid: 'Original' });
  assert.equal(h.current.ssid, 'Original');
  await h.client.act('apply', ID);
  assert.equal(h.current.ssid, 'NewName');
  await h.client.act('commit', ID);
  assert.equal(h.pending, null);
  assert.deepEqual(h.writes[0].body, { ssid: 'NewName' });
  for (const write of h.writes.slice(1)) {
    assert.equal(write.headers['X-OM-CSRF'], CSRF);
    assert.equal(write.headers['X-OM-Confirm'], 'OPENMITRASTAR_CONFIG_TRANSACTION_V1');
    assert.equal(write.headers['X-OM-Transaction'], ID);
    assert.deepEqual(write.body, { _confirm: 'OPENMITRASTAR_CONFIG_TRANSACTION_V1', _transaction: ID });
  }
});

test('rollback remains possible when new apply operations are disabled', async () => {
  const h = harness(); await h.client.prepare('2g', { ssid: 'NewName' }, { ssid: 'Original' }); await h.client.act('apply', ID);
  h.apply = false;
  await h.client.act('rollback', ID);
  assert.equal(h.current.ssid, 'Original'); assert.equal(h.pending, null);
});

test('an optional plan never stages or applies blocked channel changes', async () => {
  const h = harness();
  await assert.rejects(h.client.prepare('5g', { channel: '44' }, { channel: '36' }), error => error.code === 'blocked');
  assert.equal(h.writes.length, 0);
  assert.equal((await h.client.plan5g({ channel: '44' }, { channel: '36' })).apply_allowed, false);
  assert.deepEqual(h.writes.map(row => row.path), ['/api/v1/radios/5g/plan']);
  assert.equal(h.current.channel, 36);
});

for (const [changes, original, code] of [
  [{ ssid: 'New' }, { ssid: 'OldStaleValue' }, 'stale'],
  [{ wmm: 'yes' }, { wmm: 'true' }, 'value'],
  [{ dtim_period: '16' }, { dtim_period: '3' }, 'value'],
  [{ injected: '1' }, { injected: '0' }, 'blocked'],
]) test(`invalid/stale change cannot POST: ${JSON.stringify(changes)}`, async () => {
  const h = harness(); await assert.rejects(h.client.prepare('5g', changes, original), error => error.code === code); assert.equal(h.writes.length, 0);
});

for (const change of ['expired', 'foreign', 'different-id', 'apply-disabled']) test(`recheck prevents apply when ${change}`, async () => {
  const h = harness(); await h.client.prepare('5g', { ssid: 'New' }, { ssid: 'Original' });
  if (change === 'expired') h.pending = null;
  if (change === 'foreign') h.pending.owned_by_session = false;
  if (change === 'different-id') h.pending.transaction_id = 'c'.repeat(64);
  if (change === 'apply-disabled') h.apply = false;
  await assert.rejects(h.client.act('apply', ID)); assert.equal(h.writes.length, 1);
});

test('lost apply response is never blindly resent; reread permits rollback', async () => {
  const h = harness(); await h.client.prepare('5g', { ssid: 'New' }, { ssid: 'Original' }); h.loseApply = true;
  await assert.rejects(h.client.act('apply', ID), error => error.ambiguous);
  await assert.rejects(h.client.act('apply', ID), error => error.code === 'phase');
  assert.equal(h.writes.filter(row => row.path.endsWith('/apply')).length, 1);
  await h.client.act('rollback', ID); assert.equal(h.current.ssid, 'Original');
});

test('mismatched readback blocks commit before POST', async () => {
  const h = harness(); await h.client.prepare('5g', { ssid: 'New' }, { ssid: 'Original' }); await h.client.act('apply', ID);
  h.wrongReadback = true;
  await assert.rejects(h.client.act('commit', ID), error => error.code === 'readback');
  assert.equal(h.writes.filter(row => row.path.endsWith('/commit')).length, 0);
});

test('DFS needs capability and explicit acknowledgement, even if writable is true', async () => {
  const h = harness(); h.channelWritable = true;
  await assert.rejects(h.client.prepare('5g', { channel: '52' }, { channel: '36' }, true), error => error.code === 'dfs');
  h.dfsReady = true;
  await assert.rejects(h.client.prepare('5g', { channel: '52' }, { channel: '36' }, false), error => error.code === 'dfs');
  assert.equal(h.writes.length, 0);
  await h.client.prepare('5g', { channel: '52' }, { channel: '36' }, true);
  assert.equal(h.writes[0].headers['X-OM-Regulatory-Ack'], 'OPENMITRASTAR_ES_DFS_V1');
  h.dfsReady = false;
  await assert.rejects(h.client.act('apply', ID), error => error.code === 'dfs');
  assert.equal(h.writes.length, 1);
});

test('missing CSRF and duplicate settings fail closed', async () => {
  const h = harness(); h.csrf = '';
  await assert.rejects(h.client.prepare('5g', { ssid: 'New' }, { ssid: 'Original' }), error => error.code === 'auth');
  assert.equal(h.writes.length, 0);
  const contract = h.contract('5g'); contract.settings.settings.push(contract.settings.settings[0]);
  assert.throws(() => parseContract(contract, '5g'));
});
