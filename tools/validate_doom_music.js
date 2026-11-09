// Local-only actual browser PCM qualification. Never contacts the HGW.
const fs=require('fs'),path=require('path'),http=require('http'),crypto=require('crypto');
const {chromium}=require('/workspace/user-home/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const candidate=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]),pump=process.argv[4]==='--pump',gameplay=process.argv.includes('--gameplay');
const assets=path.resolve('outputs/doom/browser-20261022-r2-touch/www/Doom');
if(fs.existsSync(out))throw Error('Pass a NEW output');fs.mkdirSync(out,{recursive:true});
const index=fs.readFileSync(path.join(candidate,'index.html'),'utf8');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
let activeStage='setup';
const hardDeadline=setTimeout(()=>{fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'NO_GO_BROWSER_ENGINE_STALL',stage:activeStage,candidate_index_sha256:sha(index),timeout_ms:70000},null,2)+'\n');require('child_process').execFileSync('taskkill',['/PID',String(process.pid),'/T','/F']);},70000);
const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://local');
 if(url.pathname==='/Doom/'||url.pathname==='/Doom/index.html'){
  const mode=url.searchParams.get('mode')||'full',map=url.searchParams.get('map')||'1';
  let html=index;
  if(mode!=='full')html=html.replace('sfx_volume 8\\n','sfx_volume 0\\n');
  if(mode==='muted')html=html.replace('music_volume 8\\n','music_volume 0\\n');
  if(mode!=='full')html=html.replace("'-nogui','-config'",`'-nogui','-warp','1','${map}','-skill','2','-config'`);
  if(mode==='muted')html=html.replace("'-nogui','-warp'","'-nogui','-nomusic','-warp'");
  res.writeHead(200,{'Content-Type':'text/html'});res.end(html);return;
 }
 const name=url.pathname.replace('/Doom/','');if(!/^[a-zA-Z0-9_.-]+$/.test(name)){res.writeHead(404);res.end();return;}
 const file=name==='chocolate-doom.wasm'&&fs.existsSync(path.join(candidate,name))?path.join(candidate,name):path.join(assets,name);if(!fs.existsSync(file)){res.writeHead(404);res.end();return;}
 if(pump&&name==='chocolate-doom.js'){
  const before='var start = _emscripten_get_now();\n while (_emscripten_get_now() - start < msecs) {}';
  const after='var start = _emscripten_get_now();\n var ctx=Module.SDL2&&Module.SDL2.audioContext, node=Module.SDL2&&Module.SDL2.audio&&Module.SDL2.audio.scriptProcessorNode;\n if(!window.__DOOM_RUNNING__&&node&&node.onaudioprocess){console.log("[PUMP] "+msecs);var buf=ctx.createBuffer(2,node.bufferSize,ctx.sampleRate);node.onaudioprocess({outputBuffer:buf});}\n while (_emscripten_get_now() - start < msecs) {}';
  let js=fs.readFileSync(file,'utf8');if(js.split(before).length!==2)throw Error('Unexpected sleep source');js=js.replace(before,after);res.writeHead(200,{'Content-Type':'application/javascript'});res.end(js);return;
 }
 const mime=name.endsWith('.wasm')?'application/wasm':name.endsWith('.js')?'application/javascript':'application/octet-stream';
 res.writeHead(200,{'Content-Type':mime});fs.createReadStream(file).pipe(res);
});
function wav(samples,rate){const b=Buffer.alloc(44+samples.length*2);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(rate,24);b.writeUInt32LE(rate*2,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(samples.length*2,40);samples.forEach((x,i)=>b.writeInt16LE(Math.round(Math.max(-1,Math.min(1,x))*32767),44+i*2));return b;}
async function run(browser,base,mode,map){
 activeStage=`${mode}-e1m${map}: startup`;
 const page=await browser.newPage(),logs=[],errors=[],requests=[];
 page.on('console',m=>{logs.push(m.text());fs.appendFileSync(path.join(out,`${mode}-e1m${map}-console.txt`),m.text()+'\n');});page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requests.push(r.url()));
 await page.goto(base+`?mode=${mode}&map=${map}`);await page.click('#start');
 await page.waitForFunction(()=>window.__DOOM_RUNNING__===true,{timeout:45000});await page.click('#canvas');
 activeStage=`${mode}-e1m${map}: engine running`;await page.waitForTimeout(1800);
 const setup=await page.evaluate(()=>{
  const s=Module.SDL2,n=s?.audio?.scriptProcessorNode;
  if(!n)return {error:'Missing actual audio node'};
  const original=n.onaudioprocess;window.__PCM_CAPTURE__={samples:[],blocks:0,rate:s.audioContext.sampleRate};
  n.onaudioprocess=function(e){original.call(this,e);const c=window.__PCM_CAPTURE__;if(!c)return;const data=e.outputBuffer.getChannelData(0);c.blocks++;if(c.samples.length<200000)c.samples.push(...data);};
  return {audio_state:s.audioContext.state,sample_rate:s.audioContext.sampleRate,callback_present:typeof original==='function'};
 });
 activeStage=`${mode}-e1m${map}: capturing actual PCM`;await page.waitForTimeout(3200);
 const pcm=await page.evaluate(()=>{const c=window.__PCM_CAPTURE__;if(!c)return null;const s=c.samples;return {samples:s,rate:c.rate,blocks:c.blocks,state:Module.SDL2.audioContext.state,config:Module.FS.readFile('/default.cfg',{encoding:'utf8'})};});
 if(!pcm)throw Error(JSON.stringify(setup));
 const samples=pcm.samples,b=Buffer.from(new Float32Array(samples).buffer),nonzero=samples.filter(x=>Math.abs(x)>1e-6).length;
 const result={mode,map,index_sha256:sha(index),setup,audio_state:pcm.state,blocks:pcm.blocks,sample_count:samples.length,nonzero_samples:nonzero,rms:Math.sqrt(samples.reduce((a,x)=>a+x*x,0)/Math.max(1,samples.length)),peak:samples.reduce((a,x)=>Math.max(a,Math.abs(x)),0),pcm_sha256:sha(b),errors,logs,requests,config:pcm.config};
 if(mode==='full'){
  for(let i=0;i<5;i++){await page.keyboard.press('Enter');await page.waitForTimeout(300);}
  await page.waitForTimeout(500);const before=await page.locator('#canvas').screenshot();
  await page.keyboard.down('w');await page.waitForTimeout(650);await page.keyboard.up('w');const moved=await page.locator('#canvas').screenshot();
  await page.keyboard.press(' ');await page.waitForTimeout(250);const fired=await page.locator('#canvas').screenshot();
  result.movement_changed=sha(before)!==sha(moved);result.fire_changed=sha(moved)!==sha(fired);await page.screenshot({path:path.join(out,'gameplay.png')});
 }
 fs.writeFileSync(path.join(out,`${mode}-e1m${map}.wav`),wav(samples,pcm.rate));fs.writeFileSync(path.join(out,`${mode}-e1m${map}.json`),JSON.stringify(result,null,2)+'\n');
 await page.close();return result;
}
(async()=>{await new Promise(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${server.address().port}/Doom/`;
 const browser=await chromium.launch({channel:'chrome',headless:true});try{
  const muted=await run(browser,base,'muted','1'),music1=await run(browser,base,'music','1'),music2=await run(browser,base,'music','2');
  const full=gameplay?await run(browser,base,'full','1'):null;
  const tests={muted_is_silent:muted.nonzero_samples===0,music1_has_pcm:music1.nonzero_samples>1000&&music1.rms>0.0001,music2_has_pcm:music2.nonzero_samples>1000&&music2.rms>0.0001,tracks_differ:music1.pcm_sha256!==music2.pcm_sha256,all_audio_running:[muted,music1,music2].every(r=>r.audio_state==='running'),no_js_errors:[muted,music1,music2].every(r=>r.errors.length===0),no_external_requests:[muted,music1,music2].every(r=>r.requests.every(u=>u.startsWith(base.slice(0,-6))))};
  if(full){tests.default_music_has_pcm=full.nonzero_samples>1000;tests.default_play_and_fire=full.movement_changed&&full.fire_changed;tests.default_errors_empty=full.errors.length===0;}
  const result={status:Object.values(tests).every(Boolean)?'PASS_ORIGINAL_WAD_MUSIC_ACTUAL_PCM':'NO_GO_MUSIC_PCM',candidate_index_sha256:sha(index),candidate_wasm_sha256:sha(fs.readFileSync(fs.existsSync(path.join(candidate,'chocolate-doom.wasm'))?path.join(candidate,'chocolate-doom.wasm'):path.join(assets,'chocolate-doom.wasm'))),tests,runs:[muted,music1,music2,...full?[full]:[]].map(r=>({...r,logs:r.logs.filter(x=>/OPL|music|sound|game started|Failed|Error/.test(x))}))};
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));if(result.status.startsWith('NO_GO'))process.exitCode=1;
 }finally{await browser.close();await new Promise(r=>server.close(r));clearTimeout(hardDeadline);}
})().catch(e=>{console.error(e);fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({error:e.message,stage:activeStage},null,2)+'\n');server.close();process.exitCode=1;});
