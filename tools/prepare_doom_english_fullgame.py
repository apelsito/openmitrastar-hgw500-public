"""Versioned English Doom shell with local IWAD loading; no hardware."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'outputs/doom/browser-20261022-r2-touch/www/Doom/index.html'
PIN='92e5b55eb9ed45e67c95a153dc0ec0cf13ecfc6e34efe03c89302146b51bdb2c'
TRANSLATIONS={
 'lang="es"':'lang="en"',
 'SALA SECRETA':'SECRET ROOM','EPISODIO 1 · SHAREWARE':'DOOM · SHAREWARE / YOUR COPY',
 'Juego Doom':'Doom game','El clásico de 1993, servido desde este router. Pulsa jugar y entra en el primer episodio.':'The 1993 classic, served by your router. Play the free first episode or load your own full-game WAD.',
 'Jugar a DOOM':'Play DOOM','Listo para jugar':'Ready to play','Pantalla completa':'Full screen','Reiniciar':'Restart',
 'Controles táctiles':'Touch controls','Usar':'Use','Menú':'Menu','Fuego':'Fire',
 'Avanzar / retroceder':'Move forward / backward','Desplazarte lateralmente':'Strafe left / right','← / → o ratón':'← / → or mouse','Girar':'Turn','Espacio':'Space','Disparar':'Fire','Puertas e interruptores':'Doors and switches','Mayús':'Shift','Correr':'Run','Esc / Intro':'Esc / Enter','Menu / aceptar':'Menu / confirm','Mapa / armas':'Map / weapons',
 'Episodio shareware original, sin modificaciones.':'Original, unmodified shareware episode.',
 'Archivo original completo y documentación':'Complete original shareware archive and documentation',
 'Motor Chocolate Doom / Cloudflare':'Chocolate Doom / Cloudflare engine','Código fuente del motor':'Engine source code','Descompresión fflate':'fflate decompression',
 'No se pudo iniciar: ':'Could not start: ','Error al iniciar':'Startup error',
 'Archivo shareware incompleto':'Incomplete shareware archive','Instalador shareware no reconocido':'Unrecognized shareware installer','Datos Doom no válidos':'Invalid Doom data',
 'Cargando el episodio desde el router…':'Loading game data…','Este navegador necesita WebAssembly':'This browser needs WebAssembly',
 'En juego · clic en la pantalla para controlar':'Playing · click the screen to focus','Iniciando el motor…':'Starting the engine…','No se pudo cargar el motor':'Could not load the engine'
}
LOCAL_SCRIPT=r'''
let selectedGame=null;
function parseIwad(bytes,filename){
 if(bytes.byteLength<12||bytes.byteLength>67108864)throw Error('Choose an IWAD smaller than 64 MB.');
 if(String.fromCharCode(...bytes.subarray(0,4))!=='IWAD')throw Error('This is not a base-game IWAD. Mods need a base game.');
 const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),count=view.getUint32(4,true),directory=view.getUint32(8,true);
 if(!count||count>100000||directory<12||directory+count*16>bytes.length)throw Error('Invalid WAD directory.');
 const names=new Set();
 for(let i=0;i<count;i++){
  const p=directory+i*16,offset=view.getUint32(p,true),size=view.getUint32(p+4,true);
  if(size&&(offset>bytes.length||size>bytes.length-offset))throw Error('Invalid WAD lump bounds.');
  let name='';for(let j=0;j<8&&bytes[p+8+j];j++)name+=String.fromCharCode(bytes[p+8+j]);names.add(name.toUpperCase());
 }
 if(names.has('MAP01'))return {wad:bytes,name:filename.toLowerCase().includes('freedoom')?'freedoom2.wad':'doom2.wad',label:'Full game · '+filename};
 if(names.has('E1M1'))return {wad:bytes,name:names.has('E2M1')?'doom.wad':'doom1.wad',label:(names.has('E2M1')?'Full game':'Shareware')+' · '+filename};
 throw Error('Choose a Doom, Doom II or Freedoom IWAD.');
}
document.getElementById('iwad').addEventListener('change',async e=>{
 const file=e.target.files[0];if(!file)return;
 if(file.size>67108864){loading.textContent='Choose a WAD smaller than 64 MB.';e.target.value='';return;}
 try{selectedGame=parseIwad(new Uint8Array(await file.arrayBuffer()),file.name);loading.textContent=selectedGame.label+' · loaded locally';document.querySelector('.badge').textContent=selectedGame.label;document.querySelector('.box h2').textContent='Your full game';start.textContent='Play selected game';}
 catch(error){loading.textContent=error.message;e.target.value='';selectedGame=null;}
});
'''

def main():
    raw=BASE.read_bytes();assert hashlib.sha256(raw).hexdigest()==PIN
    text=raw.decode('utf-8')
    for old,new in TRANSLATIONS.items():
        assert old in text,old
        text=text.replace(old,new)
    picker='''<p class="wad-picker"><label for="iwad">Have the full game? Choose DOOM.WAD or DOOM2.WAD:</label><br><input id="iwad" type="file" accept=".wad" aria-describedby="iwad-note"><small id="iwad-note">Read locally in your browser. Your game file is never uploaded.</small></p>'''
    text=text.replace('<p id="loading" aria-live="polite"></p>',picker+'<p id="loading" aria-live="polite"></p>')
    text=text.replace('</style>','.wad-picker{font-size:13px}.wad-picker input{max-width:100%;margin:10px 0}.wad-picker small{display:block;color:#9ba3ac}\n</style>')
    text=text.replace('let running=false;','let running=false;'+LOCAL_SCRIPT)
    text=text.replace("const wad=extractDoom(await download('doom19s.zip'));const config=", "const game=selectedGame||{wad:extractDoom(await download('doom19s.zip')),name:'doom1.wad',label:'Doom Shareware'};const wad=game.wad;document.getElementById('iwad').disabled=true;const config=")
    text=text.replace("Module.FS.createDataFile('/','doom1.wad',wad", "Module.FS.createDataFile('/',game.name,wad")
    text=text.replace("callMain(['-iwad','doom1.wad'", "callMain(['-iwad',game.name")
    text=text.replace("start.disabled=false;console.error(e)","start.disabled=false;document.getElementById('iwad').disabled=false;console.error(e)")
    assert 'aceptar' not in text and 'lang="es"' not in text
    out=ROOT/'outputs/doom'/('english-fullgame-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(exist_ok=False)
    (out/'index.html').write_bytes(text.encode('utf-8'))
    script=text.split('<script>')[1].split('</script>')[0];(out/'inline.js').write_text(script,encoding='utf-8')
    result={'status':'PREPARED_ENGLISH_LOCAL_FULLGAME','source_sha256':PIN,'index_sha256':hashlib.sha256(text.encode()).hexdigest(),'bytes':len(text.encode()),'hardware_actions':False,'full_commercial_assets_bundled':False,'local_game_file_upload':False}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'directory':str(out),**result}))

if __name__=='__main__':main()
