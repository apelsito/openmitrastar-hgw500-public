"""Prepare self-contained browser Doom assets. Never accesses a router."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_COMMIT = "e892222b66fd943bf196f285292aa15b98d89a5b"
SOURCE_COMMIT = "65e0d3ae2ffa604155eebd96ed40da6567bd08f4"
ENGINE_BASE = f"https://raw.githubusercontent.com/islamMendjel/project-DOOMbr/{ENGINE_COMMIT}/"
INPUTS = {
    "chocolate-doom.js": (ENGINE_BASE + "docs/engine/chocolate-doom.js", "5dee50186df63248ddf2cc1ed8ad5f2c1fb04503845d0c4e6b7f608c6be38836"),
    "chocolate-doom.wasm": (ENGINE_BASE + "docs/engine/chocolate-doom.wasm", "6366f83a58fe8596ce742a66dbf86871d315862c89c11e65b54935be03c7e6c4"),
    "GPL-2.0.txt": (ENGINE_BASE + "CHOCOLATE-DOOM-LICENSE.txt", "aef8b4222b79d0dbf6bf17cfff71c90a6a6bb8917a4162abe417b469ed22da2e"),
    "upstream-engine.txt": (ENGINE_BASE + "docs/engine/README.md", "f2ff573ce0e999c776ecee9b2bbf2ff8673f74f360facca36c88b635afe4e1f5"),
    "doom19s.zip": ("https://www.gamers.org/pub/idgames/idstuff/doom/doom19s.zip", "cacf0142b31ca1af00796b4a0339e07992ac5f21bc3f81e7532fe1b5e1b486e6"),
    "fflate.js": ("https://unpkg.com/fflate@0.8.2/umd/index.js", "c3b34f2e9f5e74d4d7d64e01cac7a0c01954c6c406414d42185c7b53d6875ddf"),
    "fflate-LICENSE.txt": ("https://raw.githubusercontent.com/101arrowz/fflate/v0.8.2/LICENSE", "805f6cb28bb8b6d3a0badd83c93bccd9671fa01a3b4b92b7042b0743325ac243"),
    "doom-wasm-source.tar.gz": (f"https://codeload.github.com/cloudflare/doom-wasm/tar.gz/{SOURCE_COMMIT}", "9be6e02bb1f4f4b00f73d21b0c1ba4f2b8087e3c6cb1f477435baa390b3aa482"),
}

INDEX = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>DOOM · OpenMitraStar</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#0d1013;color:#eee}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 50% 10%,#35201c 0,transparent 50%)}main{max-width:1000px;margin:auto;padding:28px 20px}header{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:20px}.brand{font-size:12px;letter-spacing:.2em;color:#adb3b9}h1{font-family:Impact,'Arial Black',sans-serif;font-size:clamp(48px,10vw,96px);letter-spacing:.08em;margin:0;color:#eac89d;text-shadow:3px 4px 0 #7e2b21}.badge{font-size:12px;border:1px solid #604239;padding:7px 10px;border-radius:20px;color:#dfb392}.screen{position:relative;background:#000;border:1px solid #523b31;border-radius:10px;overflow:hidden;box-shadow:0 20px 80px #0008}canvas{display:block;width:100%;aspect-ratio:4/3;image-rendering:pixelated;outline:none}.cover{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;padding:20px;background:linear-gradient(#111b,#000e)}.cover.hidden{display:none}.box{max-width:410px}h2{font-size:28px;margin:0 0 12px}.box p{color:#bbc0c5;line-height:1.6}button{font:inherit;cursor:pointer;border:1px solid #ba6551;background:#a23928;color:#fff;padding:12px 22px;border-radius:6px;min-height:44px}button:hover{background:#c44730}button:disabled{opacity:.6;cursor:wait}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:14px 0}.toolbar button{background:#171b20;border-color:#41484e;padding:8px 13px;font-size:13px}#status{font-size:13px;color:#adb4ba}.keys{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;font-size:14px;padding:20px;background:#151a1f;border:1px solid #2e3439;border-radius:8px;color:#b9c0c7}.keys b{color:#eee}footer{font-size:12px;color:#939ba2;line-height:1.6;margin-top:22px}a{color:#c7a279}.touch{display:none;grid-template-columns:1fr 1fr;gap:20px;user-select:none;touch-action:none;margin:16px 0}.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.touch button{font-size:18px;padding:12px 5px;touch-action:none;background:#252b30;border-color:#46505a}.touch button.active{background:#9b3224}@media(pointer:coarse){.touch{display:grid}}@media(max-width:520px){main{padding:16px 10px}header{align-items:flex-start}.badge{margin-top:10px}.keys{grid-template-columns:1fr 1fr;font-size:12px;padding:14px}}
</style></head><body><main><header><div><div class="brand">OPENMITRASTAR · SALA SECRETA</div><h1>DOOM</h1></div><span class="badge">EPISODIO 1 · SHAREWARE</span></header>
<div class="screen"><canvas id="canvas" width="640" height="480" tabindex="0" aria-label="Juego Doom"></canvas><div class="cover" id="cover"><div class="box"><h2>Knee-Deep in the Dead</h2><p>El clásico de 1993, servido desde este router. Pulsa jugar y entra en el primer episodio.</p><button id="start">Jugar a DOOM</button><p id="loading" aria-live="polite"></p></div></div></div>
<div class="toolbar"><span id="status" aria-live="polite">Listo para jugar</span><div><button id="full">Pantalla completa</button> <button id="restart">Reiniciar</button></div></div>
<div class="touch" aria-label="Controles táctiles"><div class="pad"><span></span><button data-key="w">▲</button><span></span><button data-key="ArrowLeft">↶</button><button data-key="s">▼</button><button data-key="ArrowRight">↷</button></div><div class="pad"><button data-key="Enter">↵</button><button data-key="e">Usar</button><button data-key="Escape">Menú</button><button data-key="a">◀</button><button data-key=" ">Fuego</button><button data-key="d">▶</button></div></div>
<div class="keys"><span><b>W / S</b> · Avanzar / retroceder</span><span><b>A / D</b> · Desplazarte lateralmente</span><span><b>← / → o ratón</b> · Girar</span><span><b>Espacio</b> · Disparar</span><span><b>E</b> · Puertas e interruptores</span><span><b>Mayús</b> · Correr</span><span><b>Esc / Intro</b> · Menú / aceptar</span><span><b>Tab / 1–7</b> · Mapa / armas</span></div>
<footer>DOOM © 1993–1995 id Software. Episodio shareware original, sin modificaciones. <a href="/Doom/doom19s.zip" download>Archivo original completo y documentación</a><br>Motor Chocolate Doom / Cloudflare, <a href="/Doom/GPL-2.0.txt">GPL v2</a> · <a href="/Doom/doom-wasm-source.tar.gz" download>Código fuente del motor</a> · Descompresión fflate, <a href="/Doom/fflate-LICENSE.txt">MIT</a></footer></main>
<script src="/Doom/fflate.js"></script><script>
'use strict';
const canvas=document.getElementById('canvas'),start=document.getElementById('start'),cover=document.getElementById('cover'),loading=document.getElementById('loading'),status=document.getElementById('status');
let running=false;
function fail(e){loading.textContent='No se pudo iniciar: '+(e.message||e);status.textContent='Error al iniciar';start.disabled=false;console.error(e)}
async function download(path){const r=await fetch('/Doom/'+path,{credentials:'omit'});if(!r.ok)throw Error(path+': HTTP '+r.status);return new Uint8Array(await r.arrayBuffer())}
function extractDoom(bytes){const outer=fflate.unzipSync(bytes);const a=outer['DOOMS_19.1'],b=outer['DOOMS_19.2'];if(!a||!b)throw Error('Archivo shareware incompleto');const merged=new Uint8Array(a.length+b.length);merged.set(a);merged.set(b,a.length);let begin=-1;for(let i=0;i<merged.length-4;i++){if(merged[i]===80&&merged[i+1]===75&&merged[i+2]===3&&merged[i+3]===4){begin=i;break}}if(begin<0)throw Error('Instalador shareware no reconocido');const inner=fflate.unzipSync(merged);const wad=inner['DOOM1.WAD'];if(!wad||wad.length!==4196020||String.fromCharCode(...wad.subarray(0,4))!=='IWAD')throw Error('Datos Doom no válidos');return wad}
start.addEventListener('click',async()=>{start.disabled=true;loading.textContent='Cargando el episodio desde el router…';try{if(!window.WebAssembly)throw Error('Este navegador necesita WebAssembly');const wad=extractDoom(await download('doom19s.zip'));const config=`use_libsamplerate 0\naspect_ratio_correct 1\nforce_software_renderer 0\nstartup_delay 0\nshow_diskicon 1\ngrabmouse 0\nfullscreen 0\nsfx_volume 8\nmusic_volume 0\nshow_messages 1\nkey_right 77\nkey_left 75\nkey_up 17\nkey_down 31\nkey_strafeleft 30\nkey_straferight 32\nkey_fire 57\nkey_use 18\nkey_strafe 56\nkey_speed 42\nuse_mouse 1\nuse_joystick 0\nscreenblocks 10\ndetaillevel 0\nsnd_channels 8\nsnd_musicdevice 0\nsnd_sfxdevice 3\nusegamma 0\n`;
window.Module={canvas,noInitialRun:true,locateFile:p=>'/Doom/'+(p.endsWith('.wasm')?'chocolate-doom.wasm':p),preRun:()=>{Module.FS.createDataFile('/','doom1.wad',wad,true,true,true);Module.FS.createDataFile('/','default.cfg',config,true,true,true)},onRuntimeInitialized:()=>{try{callMain(['-iwad','doom1.wad','-window','-nogui','-nomusic','-config','default.cfg']);running=true;window.__DOOM_RUNNING__=true;cover.classList.add('hidden');status.textContent='En juego · clic en la pantalla para controlar';canvas.focus()}catch(e){fail(e)}},print:t=>console.log('[DOOM]',t),printErr:t=>console.warn('[DOOM]',t),onAbort:e=>fail(Error(e))};loading.textContent='Iniciando el motor…';const script=document.createElement('script');script.src='/Doom/chocolate-doom.js';script.onerror=()=>fail(Error('No se pudo cargar el motor'));document.body.appendChild(script)}catch(e){fail(e)}});
canvas.addEventListener('click',()=>canvas.focus());document.getElementById('full').onclick=()=>{const p=document.querySelector('.screen').requestFullscreen?.();p?.catch(()=>{});canvas.focus()};document.getElementById('restart').onclick=()=>location.reload();
window.addEventListener('keydown',e=>{if(running&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight',' ','Tab'].includes(e.key))e.preventDefault()},{passive:false});
const keyInfo={w:['KeyW',87],s:['KeyS',83],a:['KeyA',65],d:['KeyD',68],e:['KeyE',69],ArrowLeft:['ArrowLeft',37],ArrowRight:['ArrowRight',39],Enter:['Enter',13],Escape:['Escape',27],' ':['Space',32]};
function sendKey(key,type){const [code,keyCode]=keyInfo[key];const event=new KeyboardEvent(type,{key,code,keyCode,which:keyCode,bubbles:true,cancelable:true});document.dispatchEvent(event)}
document.querySelectorAll('[data-key]').forEach(button=>{const key=button.dataset.key;button.addEventListener('pointerdown',e=>{e.preventDefault();try{button.setPointerCapture(e.pointerId)}catch{}button.classList.add('active');sendKey(key,'keydown')});const release=e=>{e.preventDefault();if(button.classList.contains('active')){button.classList.remove('active');sendKey(key,'keyup')}};button.addEventListener('pointerup',release);button.addEventListener('pointercancel',release);button.addEventListener('lostpointercapture',release)});
window.addEventListener('blur',()=>{document.querySelectorAll('[data-key].active').forEach(b=>{b.classList.remove('active');sendKey(b.dataset.key,'keyup')})});
</script></body></html>
'''


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    target = out / "www" / "Doom"
    target.mkdir(parents=True)
    pins = {}
    for name, (url, expected) in INPUTS.items():
        request = urllib.request.Request(url, headers={"User-Agent": "OpenMitraStar-local-package"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        if sha(data) != expected:
            raise ValueError(f"Upstream hash mismatch: {name}")
        (target / name).write_bytes(data)
        pins[name] = {"url": url, "sha256": expected, "bytes": len(data)}
    outer = zipfile.ZipFile(target / "doom19s.zip")
    original = outer.read("DOOMS_19.1") + outer.read("DOOMS_19.2")
    inner = zipfile.ZipFile(io.BytesIO(original))
    wad = inner.read("DOOM1.WAD")
    if wad[:4] != b"IWAD" or len(wad) != 4196020:
        raise ValueError("Original shareware WAD malformed")
    (target / "index.html").write_text(INDEX, encoding="utf-8", newline="\n")
    notice = {
        "engine_binary_provider": "islamMendjel/project-DOOMbr", "engine_binary_commit": ENGINE_COMMIT,
        "source_repository": "cloudflare/doom-wasm", "source_commit": SOURCE_COMMIT,
        "source_provenance_limit": "Binary provider attributes engine to this upstream. Exact rebuild correspondence has not been independently demonstrated.",
        "assets": "Original Doom 1.9 shareware archive retained complete, no modified levels; WAD extracted only inside client browser.",
        "execution": "Single-player browser WebAssembly, same-origin files only, no external game service. Router only serves static files.",
        "shareware_wad_sha256": sha(wad), "shareware_wad_bytes": len(wad),
    }
    (target / "PROVENANCE.json").write_text(json.dumps(notice, indent=2)+"\n", encoding="utf-8")
    files = {p.name:{"bytes":p.stat().st_size,"sha256":sha(p.read_bytes())} for p in sorted(target.iterdir())}
    total=sum(v["bytes"] for v in files.values())
    if total > 6_000_000:
        raise ValueError(f"Static package too large: {total}")
    manifest={"status":"OFFLINE_PREPARED_PHYSICAL_UNRUN", "created_utc":dt.datetime.now(dt.timezone.utc).isoformat(), "target":"HGW-500BNA-QCv2 A2", "route":"/Doom", "homepage_link":False,"static_bytes":total,"files":files,"upstream_pins":pins,"provenance":notice}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    with tarfile.open(out/"doom-static.tar", "w") as archive:
        for p in sorted(target.iterdir()):
            info=archive.gettarinfo(str(p),arcname="Doom/"+p.name);info.uid=0;info.gid=0;info.uname="";info.gname="";info.mode=0o644;info.mtime=0
            with p.open("rb") as f:archive.addfile(info,f)
    return {"output":str(out),"static_bytes":total,"tar_sha256":sha((out/"doom-static.tar").read_bytes()),"wad_sha256":sha(wad)}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    output=args.output or ROOT/"outputs"/"doom"/("browser-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    print(json.dumps(prepare(output),indent=2))
