import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeDfs, loadDfsObservation, durationLabel } from '../src/dfs-observation.ts';

const sample = (extra = {}) => ({schema:'lyoko.radio.dfs-observation/v1',backend_ready:true,
  detector:{running:true},current_channel:100,bandwidth_mhz:80,region:'ES',cac:{state:'complete',active:false,remaining_seconds:0},
  nop:{active:false,complete:true,entries:[]},tx:{authorized:true},...extra});
const response = (payload, status=200) => new Response(JSON.stringify(payload), {status,headers:{'Content-Type':'application/json'}});
const legacyStatus = {ok:true,schema:'lyoko.radio.status/v1',id:'5g'};
const legacyDiagnostics = {ok:true,schema:'lyoko.api.diagnostics/v1',dfs:{ok:true,schema:'lyoko.radio.dfs/v1',current_channel:36,bandwidth_mhz:80,region:'ES',writable:false}};
const dfsPath = '/api/v1/radios/5g/dfs';
const diagnosticsPath = '/api/v1/diagnostics';

test('legacy ready and writable flags never grant transmission permission', () => {
  const value=normalizeDfs({schema:'lyoko.api.radar-native/v1',backend_ready:true,dfs_tx_authorized:true});
  assert.equal(value.txAuthorized,null); assert.equal(value.detectorRunning,null);
  assert.equal(normalizeDfs({schema:'lyoko.radio.dfs/v1',writable:true}).backendReady,null);
});
test('CAC and a known NOP take precedence over an inconsistent authorized field', () => {
  assert.equal(normalizeDfs(sample()).txAuthorized,true);
  for (const change of [{backend_ready:false},{detector:{running:false}},{cac:{state:'running',active:true}},
    {cac:{state:'unknown',active:false}},{nop:{active:true,complete:true,entries:[]}},
    {nop:{active:false,complete:false,entries:[]}},{nop:{active:false,complete:true,entries:[{channel:100}]}}]) {
    assert.equal(normalizeDfs(sample(change)).txAuthorized,null);
  }
  assert.equal(normalizeDfs(sample({tx:{authorized:false}})).txAuthorized,false);
});
test('null, omitted, negative and string values stay unknown; they never become a zero timer', () => {
  for (const value of [undefined,null,'0',-1,Infinity,NaN]) {
    const result=normalizeDfs(sample({cac:{state:'running',active:true,remaining_seconds:value},current_channel:value}));
    assert.equal(result.cac.remaining,null); assert.equal(result.channel,null);
  }
  assert.equal(durationLabel(null),'No publicado'); assert.equal(durationLabel(0),'0 s');
});
test('a zero remaining timer never completes CAC or enables transmission', () => {
  const value=normalizeDfs(sample({cac:{state:'running',active:true,remaining_seconds:0}}));
  assert.equal(value.cac.state,'running'); assert.equal(value.txAuthorized,null);
});
test('missing or malformed NOP inventory cannot authorize TX even when complete is asserted', () => {
  for (const entries of [undefined, null, 'unknown', [{channel:'100',remaining_seconds:1800}], [{channel:100,remaining_seconds:-1}], [{}]]) {
    const value=normalizeDfs(sample({nop:{active:false,complete:true,entries}}));
    assert.equal(value.nop.complete,false); assert.equal(value.txAuthorized,null);
  }
});
test('completed CAC with remaining time or active flag is reported inconsistent', () => {
  for(const cac of [{state:'complete',active:false,remaining_seconds:60},{state:'not-required',active:true}]) {
    const value=normalizeDfs(sample({cac})); assert.equal(value.txAuthorized,null); assert.equal(value.cac.state,'inconsistent');
  }
});
test('legacy diagnostics remain partial and empty NOP does not prove available spectrum', () => {
  const value=normalizeDfs({schema:'lyoko.api.diagnostics/v1',dfs:{schema:'lyoko.radio.dfs/v1',current_channel:36,bandwidth_mhz:80,region:'ES',writable:false,driver_raw:{cac_status:0}}});
  assert.equal(value.channel,36); assert.equal(value.backendReady,false);
  assert.equal(value.cac.active,null); assert.equal(value.nop.complete,false); assert.equal(value.txAuthorized,null);
});
test('simulation identity survives nested diagnostics and native reads', () => {
  assert.equal(normalizeDfs(sample({simulation:true})).simulation,true);
  assert.equal(normalizeDfs({schema:'lyoko.api.diagnostics/v1',simulation:true,dfs:{schema:'lyoko.radio.dfs/v1'}}).simulation,true);
});
test('missing endpoint falls back to legacy diagnostics without hiding authorization failures', async () => {
  const calls=[]; const fetcher=async path => {calls.push(path);return calls.length===1?response({error:'not-found'},404):response(legacyDiagnostics);};
  const value=await loadDfsObservation(fetcher);
  assert.equal(value.kind,'legacy'); assert.equal(value.txAuthorized,null);
  assert.deepEqual(calls,[dfsPath,diagnosticsPath]);
  for(const status of [401,403,500]) {
    let count=0; await assert.rejects(()=>loadDfsObservation(async()=>{count++;return response({},status);})); assert.equal(count,1);
  }
});

test('the exact legacy 5 GHz status alias falls back to partial diagnostics, never TX authority', async () => {
  const calls=[];
  const value=await loadDfsObservation(async path=>{calls.push(path);return response(calls.length===1?legacyStatus:legacyDiagnostics);});
  assert.deepEqual(calls,[dfsPath,diagnosticsPath]);
  assert.equal(value.kind,'legacy'); assert.equal(value.endpoint,diagnosticsPath);
  assert.equal(value.channel,36); assert.equal(value.bandwidth,80); assert.equal(value.region,'ES');
  assert.equal(value.backendReady,false); assert.equal(value.detectorRunning,null);
  assert.equal(value.cac.state,'unknown'); assert.equal(value.cac.remaining,null);
  assert.equal(value.nop.complete,false); assert.equal(value.txAuthorized,null);
});

test('legacy fallback ignores asserted readiness, authorization and completed timers', async () => {
  const calls=[];
  const diagnostics={...legacyDiagnostics,dfs:{...sample(),ok:true,schema:'lyoko.radio.dfs/v1',writable:true,dfs_tx_authorized:true}};
  const value=await loadDfsObservation(async path=>{calls.push(path);return response(calls.length===1?legacyStatus:diagnostics);});
  assert.deepEqual(calls,[dfsPath,diagnosticsPath]);
  assert.equal(value.kind,'legacy'); assert.equal(value.backendReady,true);
  assert.equal(value.cac.state,'unknown'); assert.equal(value.cac.remaining,null);
  assert.equal(value.nop.complete,false); assert.equal(value.txAuthorized,null);
});

test('status aliases with another identity, missing success or an unknown schema do not fall back', async () => {
  for(const payload of [{...legacyStatus,id:'2g'},{...legacyStatus,id:undefined},
    {...legacyStatus,ok:false},{...legacyStatus,ok:undefined},{...legacyStatus,ok:'true'},
    {...legacyStatus,schema:'lyoko.radio.status/v2'},{ok:true,backend_ready:true},null,[]]) {
    const calls=[];
    await assert.rejects(()=>loadDfsObservation(async path=>{calls.push(path);return response(payload);}));
    assert.deepEqual(calls,[dfsPath]);
  }
});

test('native read failures are not hidden by the legacy fallback', async () => {
  for(const fetchResponse of [
    ...[401,403,500,502,503].map(status=>()=>response({},status)),
    ()=>new Response('{invalid JSON',{status:200,headers:{'Content-Type':'application/json'}}),
    ()=>new Response('{invalid JSON',{status:404,headers:{'Content-Type':'application/json'}}),
    ()=>response(null,404),
    ()=>response([],404),
    ()=>{throw new TypeError('offline');},
    ()=>{throw new DOMException('aborted','AbortError');},
  ]) {
    const calls=[];
    await assert.rejects(()=>loadDfsObservation(async path=>{calls.push(path);return fetchResponse();}));
    assert.deepEqual(calls,[dfsPath]);
  }
});

test('malformed or non-legacy diagnostics cannot become an observation after the status alias', async () => {
  for(const payload of [null,[],{},
    {...legacyDiagnostics,ok:false},{...legacyDiagnostics,ok:undefined},
    {...legacyDiagnostics,schema:'unknown'},
    {...legacyDiagnostics,dfs:null},{...legacyDiagnostics,dfs:[]},{...legacyDiagnostics,dfs:{}},
    {...legacyDiagnostics,dfs:{...legacyDiagnostics.dfs,ok:false}},
    {...legacyDiagnostics,dfs:{...legacyDiagnostics.dfs,ok:undefined}},
    {...legacyDiagnostics,dfs:{ok:true,schema:'unknown'}},
    {...legacyDiagnostics,dfs:{...sample(),ok:true}},sample()]) {
    const calls=[];
    await assert.rejects(()=>loadDfsObservation(async path=>{calls.push(path);return response(calls.length===1?legacyStatus:payload);}));
    assert.deepEqual(calls,[dfsPath,diagnosticsPath]);
  }
});

test('fallback diagnostics failures remain errors without a third request', async () => {
  for(const fetchResponse of [
    ...[401,403,404,500,502,503].map(status=>()=>response({},status)),
    ()=>new Response('{invalid JSON',{status:200,headers:{'Content-Type':'application/json'}}),
    ()=>{throw new TypeError('offline');},
    ()=>{throw new DOMException('aborted','AbortError');},
  ]) {
    const calls=[];
    await assert.rejects(()=>loadDfsObservation(async path=>{calls.push(path);return calls.length===1?response(legacyStatus):fetchResponse();}));
    assert.deepEqual(calls,[dfsPath,diagnosticsPath]);
  }
});

test('a recognized native observation never switches to legacy data to hide contradictions', async () => {
  const calls=[];
  const value=await loadDfsObservation(async path=>{calls.push(path);return response(sample({cac:{state:'running',active:true,remaining_seconds:0}}));});
  assert.deepEqual(calls,[dfsPath]);
  assert.equal(value.kind,'native'); assert.equal(value.cac.state,'running'); assert.equal(value.txAuthorized,null);
});
test('invalid schema cannot be presented as an observed backend', () => {
  assert.throws(()=>normalizeDfs({ok:true,backend_ready:true}),/contrato DFS/);
});
