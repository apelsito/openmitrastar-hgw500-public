// Actual browser controls/audio over pinned HGW HTTPS; all assets stay on HGW.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/workspace/user-home/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out=path.resolve(process.argv[2]);if(fs.existsSync(out))throw Error('New immutable evidence directory required');fs.mkdirSync(out,{recursive:true});
const spki='rB2hXlfvArj1id6BlPzqHg3FR8D+f/z7V5u3/cCCAi4=';
const origin='https://192.168.1.91';const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
(async()=>{let browser,stage='launch';try{
 browser=await chromium.launch({channel:'chrome',headless:true,args:['--ignore-certificate-errors-spki-list='+spki,'--autoplay-policy=no-user-gesture-required']});
 const results=[];
 for(const touch of [false,true]){
  const page=await browser.newPage(touch?{viewport:{width:390,height:844},isMobile:true,hasTouch:true}:{viewport:{width:1200,height:1000}});
  const errors=[],requests=[],consoleLines=[],websockets=[];
  page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.text().startsWith('[DOOM]'))consoleLines.push(m.text())});page.on('websocket',w=>websockets.push(w.url()));
  stage=(touch?'touch':'desktop')+'-landing';await page.goto(origin+'/Doom/index.html',{timeout:30000});await page.screenshot({path:path.join(out,stage+'.png'),fullPage:true});
  stage=(touch?'touch':'desktop')+'-startup';await page.click('#start');await page.waitForFunction(()=>window.__DOOM_RUNNING__===true,{timeout:45000});await page.click('#canvas');await page.waitForTimeout(1200);
  const audio=await page.evaluate(()=>{
   const s=Module.SDL2,n=s?.audio?.scriptProcessorNode;if(!n)return {present:false};
   const original=n.onaudioprocess;window.__PCM={blocks:0,count:0,energy:0,nonzero:0,peak:0};
   n.onaudioprocess=function(e){original.call(this,e);const p=window.__PCM;const data=e.outputBuffer.getChannelData(0);p.blocks++;for(const x of data){p.count++;p.energy+=x*x;if(Math.abs(x)>1e-6)p.nonzero++;p.peak=Math.max(p.peak,Math.abs(x));}};
   return {present:true,state:s.audioContext.state,rate:s.audioContext.sampleRate,config:Module.FS.readFile('/default.cfg',{encoding:'utf8'})};
  });
  await page.waitForTimeout(1600);for(let i=0;i<5;i++){await page.keyboard.press('Enter');await page.waitForTimeout(250)}await page.waitForTimeout(400);
  const before=await page.locator('#canvas').screenshot();
  if(touch){await page.evaluate(()=>document.querySelector('[data-key="w"]').dispatchEvent(new PointerEvent('pointerdown',{pointerId:7,bubbles:true})));await page.waitForTimeout(650);await page.evaluate(()=>document.querySelector('[data-key="w"]').dispatchEvent(new PointerEvent('pointerup',{pointerId:7,bubbles:true})));}
  else {await page.keyboard.down('w');await page.waitForTimeout(650);await page.keyboard.up('w');}
  const moved=await page.locator('#canvas').screenshot();await page.keyboard.press(' ');await page.waitForTimeout(300);const fired=await page.locator('#canvas').screenshot();
  const pcm=await page.evaluate(()=>({...window.__PCM,rms:Math.sqrt((window.__PCM?.energy||0)/Math.max(1,window.__PCM?.count||0))}));
  await page.screenshot({path:path.join(out,(touch?'touch':'desktop')+'-gameplay.png'),fullPage:true});
  results.push({touch,wasm_running:await page.evaluate(()=>window.__DOOM_RUNNING__===true),game_started:consoleLines.some(x=>x.includes('game started')),movement_changed:sha(before)!==sha(moved),fire_changed:sha(moved)!==sha(fired),audio,pcm,errors,websockets,requests,external:requests.filter(x=>!x.startsWith(origin+'/')),consoleLines});await page.close();
 }
 const pass=results.every(r=>r.wasm_running&&r.game_started&&r.movement_changed&&r.fire_changed&&r.audio.present&&r.audio.state==='running'&&r.pcm.nonzero>1000&&r.pcm.rms>0.0001&&!r.errors.length&&!r.websockets.length&&!r.external.length);
 const result={status:pass?'PASS_DOOM73_HGW_HTTPS_GAMEPLAY_TOUCH_AUDIO':'DOOM73_BROWSER_INCOMPLETE',url:origin+'/Doom/index.html',tls_spki_pin:spki,ignore_all_certificate_errors:false,router_kernel:'7.3.0-openmitrastar-radio73-v1',asset_wasm_sha256:'eb47045e861708f4263f994610ed2e58ab63838aff738e3577cca9b68797c20e',results,persistent:false};
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));if(!pass)process.exitCode=1;
}catch(e){fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({stage,error:e.message},null,2)+'\n');throw e;}finally{if(browser)await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
