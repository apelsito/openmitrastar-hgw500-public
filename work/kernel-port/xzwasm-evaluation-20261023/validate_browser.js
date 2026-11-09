// Local routed HTTPS origin: validates browser execution, not HGW TLS transport.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/workspace/user-home/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
if(fs.existsSync(out))throw Error('Immutable evidence directory exists');
fs.mkdirSync(out,{recursive:true});
const origin='https://doom-xz-test.invalid',digest=b=>crypto.createHash('sha256').update(b).digest('hex');
const assetManifest=JSON.parse(fs.readFileSync(path.join(root,'../../package-result.json'),'utf8'));
const mime=f=>f.endsWith('.html')?'text/html':f.endsWith('.js')?'application/javascript':f.endsWith('.json')?'application/json':'application/octet-stream';
(async()=>{
 let browser,stage='launch';const results=[];
 try{
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--autoplay-policy=no-user-gesture-required']});
  for(const touch of [false,true]){
   stage=touch?'touch':'desktop';
   const page=await browser.newPage(touch?{viewport:{width:390,height:844},isMobile:true,hasTouch:true}:{viewport:{width:1200,height:1000}});
   const requests=[],errors=[],external=[],lines=[],sockets=[];
   await page.route('**/*',async route=>{
    const url=route.request().url();requests.push(url);
    if(url.startsWith('data:')||url.startsWith('blob:'))return route.continue();
    if(!url.startsWith(origin+'/')){external.push(url);return route.abort();}
    const name=decodeURIComponent(new URL(url).pathname).replace(/^\/Doom\//,'');
    const p=path.resolve(root,name);
    if(!p.startsWith(root+path.sep)||!fs.existsSync(p)||!fs.statSync(p).isFile())return route.fulfill({status:404,body:'Not found'});
    await route.fulfill({status:200,contentType:mime(name),headers:{'Cache-Control':'no-store'},body:fs.readFileSync(p)});
   });
   page.on('pageerror',e=>errors.push(e.message));page.on('websocket',s=>sockets.push(s.url()));
   page.on('console',m=>{if(m.text().startsWith('[DOOM]'))lines.push(m.text());});
   await page.goto(origin+'/Doom/index.html',{timeout:20000});
   await page.click('#start');await page.waitForFunction(()=>window.__DOOM_RUNNING__===true,null,{timeout:45000});
   await page.click('#canvas');await page.waitForTimeout(1200);
   const audio=await page.evaluate(()=>{
    const s=Module.SDL2,n=s?.audio?.scriptProcessorNode;
    if(!n)return {present:false};
    const original=n.onaudioprocess;window.__PCM={blocks:0,count:0,energy:0,nonzero:0,peak:0};
    n.onaudioprocess=function(e){original.call(this,e);const p=window.__PCM;for(const x of e.outputBuffer.getChannelData(0)){p.count++;p.energy+=x*x;if(Math.abs(x)>1e-6)p.nonzero++;p.peak=Math.max(p.peak,Math.abs(x));}p.blocks++;};
    return {present:true,state:s.audioContext.state,config:Module.FS.readFile('/default.cfg',{encoding:'utf8'})};
   });
   await page.waitForTimeout(1200);
   for(let i=0;i<5;i++){await page.keyboard.press('Enter');await page.waitForTimeout(250);}
   await page.waitForTimeout(500);const before=await page.locator('#canvas').screenshot();
   if(touch){
    await page.evaluate(()=>document.querySelector('[data-key="w"]').dispatchEvent(new PointerEvent('pointerdown',{pointerId:7,bubbles:true})));
    await page.waitForTimeout(650);
    await page.evaluate(()=>document.querySelector('[data-key="w"]').dispatchEvent(new PointerEvent('pointerup',{pointerId:7,bubbles:true})));
   }else{await page.keyboard.down('w');await page.waitForTimeout(650);await page.keyboard.up('w');}
   const moved=await page.locator('#canvas').screenshot();
   await page.keyboard.press(' ');await page.waitForTimeout(300);const fired=await page.locator('#canvas').screenshot();
   const observed=await page.evaluate(async()=>{
    const hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
    const wad=Module.FS.readFile('/doom1.wad');
    return {assets:window.__DOOM_XZ_ASSETS__,wad_sha256:hex(await crypto.subtle.digest('SHA-256',wad)),pcm:{...window.__PCM,rms:Math.sqrt(window.__PCM.energy/Math.max(1,window.__PCM.count))}};
   });
   await page.screenshot({path:path.join(out,stage+'-gameplay.png'),fullPage:true});
   const noUncompressedFetch=!requests.some(x=>/\/Doom\/(doom19s\.zip|chocolate-doom\.(js|wasm))$/.test(x));
   const allDecodedAssets=assetManifest.assets.every(pin=>observed.assets.some(row=>row.name===pin.name&&row.sha256===pin.uncompressed_sha256&&row.decodedBytes===pin.uncompressed_bytes));
   results.push({touch,wasm_running:await page.evaluate(()=>window.__DOOM_RUNNING__===true),game_started:lines.some(x=>x.includes('game started')),movement_changed:digest(before)!==digest(moved),fire_changed:digest(moved)!==digest(fired),audio,observed,allDecodedAssets,noUncompressedFetch,errors,external,sockets,requests});
   await page.close();
  }
  // A corrupted but same-size compressed file must be rejected before decoding.
  stage='corrupt-integrity';
  const page=await browser.newPage();
  await page.route('**/*',async route=>{
   const url=route.request().url();
   if(!url.startsWith(origin+'/'))return route.abort();
   const name=decodeURIComponent(new URL(url).pathname).replace(/^\/Doom\//,'');
   const p=path.resolve(root,name);
   if(!p.startsWith(root+path.sep)||!fs.existsSync(p))return route.fulfill({status:404,body:'Not found'});
   const body=fs.readFileSync(p);if(name==='doom1.wad.xz')body[10]^=1;
   await route.fulfill({status:200,contentType:mime(name),body});
  });
  await page.goto(origin+'/Doom/index.html');await page.click('#start');
  await page.waitForFunction(()=>document.querySelector('#loading').textContent.includes('integrity failed'),null,{timeout:15000});
  const rejected=await page.evaluate(()=>({message:document.querySelector('#loading').textContent,game_started:window.__DOOM_RUNNING__===true,decoded_assets:window.__DOOM_XZ_ASSETS__||[],retry_enabled:!document.querySelector('#start').disabled}));
  await page.close();
  const pass=results.every(r=>r.wasm_running&&r.game_started&&r.movement_changed&&r.fire_changed&&r.audio.present&&r.audio.state==='running'&&r.audio.config.includes('snd_musicdevice 3')&&r.observed.pcm.nonzero>1000&&r.observed.pcm.rms>0.0001&&r.allDecodedAssets&&r.noUncompressedFetch&&!r.errors.length&&!r.external.length&&!r.sockets.length)&&!rejected.game_started&&!rejected.decoded_assets.length&&rejected.retry_enabled;
  const result={status:pass?'PASS_LOCAL_BROWSER_XZ_GAMEPLAY_TOUCH_AUDIO_INTEGRITY':'INCOMPLETE_LOCAL_BROWSER_XZ',hardware_accessed:false,HGW_transport_tested:false,origin_mode:'Playwright route fulfilled HTTPS origin; no TLS server or device mutation',playable_set_bytes:assetManifest.playable_set_bytes,results,corruption_rejection:rejected};
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({status:result.status,playable_set_bytes:result.playable_set_bytes,results:results.map(r=>({touch:r.touch,running:r.wasm_running,movement:r.movement_changed,fire:r.fire_changed,pcm:r.observed.pcm,errors:r.errors,allDecodedAssets:r.allDecodedAssets,noUncompressedFetch:r.noUncompressedFetch})),corruption_rejection:rejected},null,2));
  if(!pass)process.exitCode=1;
 }catch(e){fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({stage,error:e.message},null,2)+'\n');throw e;}
 finally{if(browser)await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
