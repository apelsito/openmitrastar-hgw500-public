import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CHANNEL_CATALOGUE, describeChannel, channelLabelForWidth } from '../src/channel-policy.ts';

test('catalogue includes all current ES DFS primaries and upper channels for inspection', () => {
  for (const channel of [52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144,149,165,177]) assert.ok(CHANNEL_CATALOGUE.includes(channel));
});
test('normal CAC and radar NOP are distinct timers', () => {
  assert.equal(describeChannel(36,20).cacSeconds,0);
  assert.equal(describeChannel(100,20).cacSeconds,60);
  assert.equal(describeChannel(100,20).nopSeconds,1800);
  assert.equal(describeChannel(124,20).cacSeconds,600);
});
test('weather-band overlap is based on full nominal bandwidth', () => {
  assert.equal(describeChannel(116,20).cacSeconds,60);
  assert.equal(describeChannel(116,40).cacSeconds,600);
  assert.equal(describeChannel(116,80).cacSeconds,600);
});
test('crossing the documented upper band edge is not declared compliant', () => {
  assert.equal(describeChannel(140,20).category,'dfs');
  assert.equal(describeChannel(140,80).category,'outside-profile');
  assert.equal(describeChannel(149,20).category,'outside-profile');
});
test('manual unknown channels do not invent frequencies or CAC times', () => {
  const value=describeChannel(200,20);
  assert.equal(value.category,'unknown');
  assert.equal(value.lowMHz,null);
  assert.equal(value.cacSeconds,null);
});
test('classic labels distinguish bandwidth-sensitive CAC and unverified channels', () => {
  assert.match(channelLabelForWidth(116,20), /CAC 60 s/);
  assert.match(channelLabelForWidth(116,80), /CAC 10 min/);
  assert.match(channelLabelForWidth(149,20), /fuera del perfil/);
});
