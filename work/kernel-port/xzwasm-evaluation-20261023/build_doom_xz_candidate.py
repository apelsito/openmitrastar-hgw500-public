"""Offline packaging candidate: original engine and WAD preserved byte for byte.

Does not modify an existing package or the HGW. Includes preserved original
archive and sources separately so full-delivery and playable-set costs are
reported honestly.
"""
from pathlib import Path
import argparse,hashlib,json,lzma,shutil,zipfile,io
WORKSPACE=Path('/workspace/user-home/Desktop/MitraStar')
HERE=Path(__file__).resolve().parent
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
def sha(data):return hashlib.sha256(data).hexdigest()
def require(ok,message):
 if not ok:raise RuntimeError(message)
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 require(not args.output.exists(),'Immutable output already exists')
 args.output.mkdir(mode=0o700);game=args.output/'www/Doom';game.mkdir(parents=True)
 old=BASE/'radioeth73-doom-complete-size-v1/root/www/Doom'
 archive=(old/'doom19s.zip').read_bytes()
 require(sha(archive)=='cacf0142b31ca1af00796b4a0339e07992ac5f21bc3f81e7532fe1b5e1b486e6','Original archive pin mismatch')
 with zipfile.ZipFile(io.BytesIO(archive)) as z:
  merged=z.read('DOOMS_19.1')+z.read('DOOMS_19.2')
 with zipfile.ZipFile(io.BytesIO(merged)) as z:wad=z.read('DOOM1.WAD')
 require(len(wad)==4196020 and wad[:4]==b'IWAD','Shareware WAD extraction mismatch')
 wasm=(old/'chocolate-doom.wasm').read_bytes()
 require(sha(wasm)=='eb47045e861708f4263f994610ed2e58ab63838aff738e3577cca9b68797c20e','Qualified engine pin mismatch')
 decoder=WORKSPACE/'work/kernel-port/xzwasm-evaluation-20261023/release/xzwasm.min.js'
 require(sha(decoder.read_bytes())=='fb7e7a0e39df438276f290dd15865734d1b81674084cfa36ef0b77042391df9b','Decoder release pin mismatch')
 shutil.copyfile(decoder,game/'xzwasm.min.js')
 rows=[]
 for name,data in [('chocolate-doom.wasm',wasm),('doom1.wad',wad),('chocolate-doom.js',(old/'chocolate-doom.js').read_bytes())]:
  compressed=lzma.compress(data,format=lzma.FORMAT_XZ,check=lzma.CHECK_CRC64,preset=9|lzma.PRESET_EXTREME)
  require(lzma.decompress(compressed)==data,'XZ round trip mismatch')
  (game/(name+'.xz')).write_bytes(compressed)
  rows.append({'name':name,'uncompressed_bytes':len(data),'uncompressed_sha256':sha(data),'xz_bytes':len(compressed),'xz_sha256':sha(compressed)})
 # Offline candidate retains all downloadable source/archive/license records.
 for p in old.iterdir():
  if p.name in ('chocolate-doom.wasm','chocolate-doom.js','fflate.js','index.html'):continue
  shutil.copyfile(p,game/p.name)
 require((game/'doom19s.zip').read_bytes()==archive,'Original archive retention failed')
 pins={r['name']:{'bytes':r['uncompressed_bytes'],'sha256':r['uncompressed_sha256'],'compressedBytes':r['xz_bytes'],'compressedSha256':r['xz_sha256']} for r in rows}
 loader=(HERE/'xz-loader-template.js').read_text().replace('__ASSET_PINS__',json.dumps(pins,separators=(',',':')))
 (game/'xz-loader.js').write_text(loader)
 index=(old/'index.html').read_text()
 index=index.replace('<script src="/Doom/fflate.js"></script>','<script src="/Doom/xzwasm.min.js"></script><script src="/Doom/xz-loader.js"></script>')
 index=index.replace("const wad=extractDoom(await download('doom19s.zip'));","const wad=await DoomXZ.download('doom1.wad');const wasm=await DoomXZ.download('chocolate-doom.wasm');")
 index=index.replace('window.Module={canvas,noInitialRun:true,','window.Module={canvas,noInitialRun:true,wasmBinary:wasm,')
 old_script="const script=document.createElement('script');script.src='/Doom/chocolate-doom.js';script.onerror=()=>fail(Error('Could not load the engine'));document.body.appendChild(script)"
 replacement="const glue=await DoomXZ.download('chocolate-doom.js');const url=URL.createObjectURL(new Blob([glue],{type:'application/javascript'}));const script=document.createElement('script');script.src=url;script.onload=()=>URL.revokeObjectURL(url);script.onerror=()=>{URL.revokeObjectURL(url);fail(Error('Could not load the engine'))};document.body.appendChild(script)"
 require(old_script in index,'Engine startup template drift');index=index.replace(old_script,replacement)
 # The original ZIP remains a download; startup uses the exact extracted WAD.
 start=index.index('function extractDoom(bytes)')
 end=index.index("\nstart.addEventListener('click'",start)
 index=index[:start]+index[end:]
 index=index.replace('Complete original shareware archive and documentation','Complete original shareware archive and documentation')
 require('fflate.' not in index and 'wasmBinary:wasm' in index,'Candidate startup integration failed')
 (game/'index.html').write_text(index)
 runtime_names={'index.html','xz-loader.js','xzwasm.min.js','chocolate-doom.wasm.xz','doom1.wad.xz','chocolate-doom.js.xz','GPL-2.0.txt','fflate-LICENSE.txt','upstream-engine.txt','PROVENANCE.json','source-equivalent.patch'}
 inventory=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes()),'runtime_set':p.name in runtime_names} for p in sorted(game.iterdir())]
 result={'status':'OFFLINE_XZ_PACKAGE_ROUNDTRIP_PASS_BROWSER_UNRUN','hardware_accessed':False,'flash_writes':0,'engine_changed':False,'music_removed':False,'episode_changed':False,'original_archive_and_sources_retained':True,'xzwasm_version':'0.1.2','xzwasm_release_date':'2021-07-04','xzwasm_commit':'75a7519c7c38fe641a9fa9809db1378fe339ac5c','assets':rows,'inventory':inventory,'original_11file_raw_bytes':sum(p.stat().st_size for p in old.iterdir()),'playable_set_bytes':sum(r['bytes'] for r in inventory if r['runtime_set']),'full_preserved_package_bytes':sum(r['bytes'] for r in inventory),'limits':['Offline candidate only; no HGW changes or firmware flash fit claimed.','Playable set excludes retained source archive and original DOS distribution; these remain in this candidate.','Raw file reduction is not the same as additional savings inside already-XZ-compressed SquashFS.']}
 (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ['status','assets','playable_set_bytes','full_preserved_package_bytes','original_11file_raw_bytes']},indent=2))
if __name__=='__main__':main()
