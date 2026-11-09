// Real browser smoke/controls test. Optional argv2 URL; argv3 immutable evidence folder.
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {chromium}=require('/workspace/user-home/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const base=process.argv[2]||'http://127.0.0.1:8766/Doom/';
const out=process.argv[3];
if(!out)throw Error('Pass a NEW evidence output directory');
if(fs.existsSync(out))throw Error('Evidence directory already exists');
fs.mkdirSync(out,{recursive:true});
function digest(bytes){return crypto.createHash('sha256').update(bytes).digest('hex')}
async function frame(p){return p.locator('#canvas').screenshot()}
async function enterGame(p){await p.click('#start');await p.waitForFunction(()=>window.__DOOM_RUNNING__,{timeout:45000});await p.waitForTimeout(1200);for(let i=0;i<5;i++){await p.keyboard.press('Enter');await p.waitForTimeout(400)}await p.waitForTimeout(600)}
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
const page=await browser.newPage({viewport:{width:1280,height:1000}}),requests=[],errors=[],stdout=[],websockets=[];
page.on('request',r=>requests.push(r.url()));page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.text().startsWith('[DOOM]'))stdout.push(m.text())});page.on('websocket',w=>websockets.push(w.url()));
await page.goto(base);await page.screenshot({path:path.join(out,'landing.png'),fullPage:true});await enterGame(page);
const before=await frame(page);await page.keyboard.down('w');await page.waitForTimeout(700);await page.keyboard.up('w');await page.waitForTimeout(100);const moved=await frame(page);
await page.keyboard.press(' ');await page.waitForTimeout(450);const fired=await frame(page);await page.screenshot({path:path.join(out,'game.png'),fullPage:true});
const origin=new URL(base).origin;const external=requests.filter(u=>!u.startsWith(origin+'/'));
const result={status:'BROWSER_GAME_PASS',url:base,wasm_running:await page.evaluate(()=>window.__DOOM_RUNNING__===true),doom_game_started:stdout.some(t=>t.includes('doom: 10, game started')),single_player:stdout.some(t=>t.includes('player 1 of 1')),movement_frame_changed:digest(before)!==digest(moved),shot_frame_changed:digest(moved)!==digest(fired),external_requests:external,websockets,errors,requests,stdout};
await page.keyboard.press('F2');await page.waitForTimeout(200);await page.keyboard.press('Enter');await page.keyboard.type('OPENMITRASTAR');await page.keyboard.press('Enter');await page.waitForTimeout(300);
result.save_virtual_paths=await page.evaluate(()=>{const walk=(p)=>{let result=[];try{for(const f of Module.FS.readdir(p)){if(f==='.'||f==='..')continue;const n=p+'/'+f,s=Module.FS.stat(n);if(Module.FS.isDir(s.mode))result=result.concat(walk(n));else if(n.endsWith('.dsg'))result.push(n)}}catch{}return result};return walk('/libsdl')});
await page.close();const touch=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});await touch.goto(base);await enterGame(touch);const tb=await frame(touch);await touch.evaluate(()=>{const b=document.querySelector('[data-key="w"]');b.dispatchEvent(new PointerEvent('pointerdown',{pointerId:1,bubbles:true}))});await touch.waitForTimeout(700);await touch.evaluate(()=>{const b=document.querySelector('[data-key="w"]');b.dispatchEvent(new PointerEvent('pointerup',{pointerId:1,bubbles:true}))});await touch.waitForTimeout(100);const ta=await frame(touch);result.touch_movement_changed=digest(tb)!==digest(ta);await touch.screenshot({path:path.join(out,'touch-game.png'),fullPage:true});await touch.close();
if(!result.wasm_running||!result.doom_game_started||!result.movement_frame_changed||external.length||websockets.length||errors.length){result.status='BROWSER_NO_GO'}
fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({...result,stdout:result.stdout.length,requests:result.requests.length},null,2));if(result.status!=='BROWSER_GAME_PASS')process.exitCode=1;
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
