import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const manifest = JSON.parse(readFileSync(resolve(root, 'reference/classic-provenance.json'), 'utf8'));
const hash = data => createHash('sha256').update(data).digest('hex');

test('original Movistar and Telefonica logos are byte-identical to pinned F314 extraction', () => {
  assert.equal(manifest.source_rootfs_sha256, 'ee2c7a63ee738382ba8eaf813cfd725e64e52ce0686bfbf83129a78dcf323cce');
  for (const path of ['public/assets/movistar-logo.svg', 'public/assets/telefonica-logo.svg', 'public/assets/movistar-m.png']) {
    const asset = manifest.files.find(item => item.path === path);
    assert.ok(asset, path);
    assert.equal(hash(readFileSync(resolve(root, path))), asset.sha256);
  }
});

test('all four original stylesheets and the transitional controller are preserved', () => {
  for (const name of ['app.css', 'layout-fixes.css', 'capabilities.css', 'f313-console.css', 'controller.js']) {
    const path = 'src/classic/' + name;
    assert.equal(hash(readFileSync(resolve(root, path))), manifest.files.find(item => item.path === path).sha256);
  }
});

test('generated TSX retains the complete classic DOM identity', () => {
  const source = readFileSync(resolve(root, 'src/classic/ClassicMarkup.tsx'), 'utf8');
  const ids = [...source.matchAll(/\bid=\{"([^"\n]+)"\}/g)].map(match => match[1]);
  assert.equal(ids.length, 139);
  assert.deepEqual(ids, manifest.dom_ids);
  for (const id of ['primary-nav','r5-channel','dfs-risk-dialog','setting-inspector','profile-apply','transaction-review','apply','rollback','packages-panel']) assert.ok(ids.includes(id), id);
});

test('the default app is the classic presentation, not the experimental redesign', () => {
  const entry = readFileSync(resolve(root, 'src/main.tsx'), 'utf8');
  assert.match(entry, /from "\.\/classic-app"/);
  assert.doesNotMatch(entry, /import "\.\/styles\.css"/);
  const app = readFileSync(resolve(root, 'src/classic-app.tsx'), 'utf8');
  assert.match(app, /ClassicMarkup/);
  for (const name of ['app.css','layout-fixes.css','capabilities.css','f313-console.css']) assert.ok(app.includes(name));
});
