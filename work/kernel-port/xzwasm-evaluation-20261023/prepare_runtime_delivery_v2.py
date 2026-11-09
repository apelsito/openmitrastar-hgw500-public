"""Prepare compact playable assets and a separate preserved local source bundle."""
from pathlib import Path
import hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'outputs/doom/xzwasm-candidate-20261023-v1'
OUT=ROOT/'outputs/doom/xzwasm-runtime-delivery-20261023-v3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 parent=json.loads((SOURCE/'package-result.json').read_text(encoding='utf-8'))
 OUT.mkdir();runtime=OUT/'www/Doom';runtime.mkdir(parents=True);sidecar=OUT/'source-and-original';sidecar.mkdir()
 records=[]
 for row in parent['inventory']:
  src=SOURCE/'www/Doom'/row['name']
  if sha(src)!=row['sha256']:raise RuntimeError('Pinned candidate asset changed')
  dest=(runtime if row['runtime_set'] else sidecar)/row['name']
  shutil.copyfile(src,dest)
  records.append({'name':row['name'],'location':'runtime' if row['runtime_set'] else 'source-and-original','parent_sha256':row['sha256']})
 # Preserve original attribution alongside corrected current delivery metadata.
 shutil.copyfile(runtime/'PROVENANCE.json',sidecar/'PROVENANCE-v1.json')
 prov=json.loads((runtime/'PROVENANCE.json').read_text(encoding='utf-8'))
 prov['assets']='Exact original Doom 1.9 shareware WAD extracted at build time, XZ packaged without data modification. Complete original DOS archive preserved in source-and-original delivery directory.'
 prov['delivery']='Router contains playable compressed assets. Complete original DOS ZIP and engine source archive accompany the local firmware delivery; no external runtime fetch required.'
 prov['xz_decompressor']={'repository':'SteveSanderson/xzwasm','version':'0.1.2','release_date':'2021-07-04','min_js_sha256':'fb7e7a0e39df438276f290dd15865734d1b81674084cfa36ef0b77042391df9b','license_notice':'MIT; embedded xz-embedded public domain and walloc MIT notices remain in bundled script banner'}
 (runtime/'PROVENANCE.json').write_text(json.dumps(prov,indent=2)+'\n',encoding='utf-8')
 index=(runtime/'index.html').read_text(encoding='utf-8')
 start=index.index('<footer>');end=index.index('</footer>',start)+len('</footer>')
 index=index[:start]+'''<footer>DOOM © 1993–1995 id Software. Original, unmodified shareware episode.<br>Chocolate Doom / Cloudflare engine · <a href="/Doom/GPL-2.0.txt">GPL v2</a> · <a href="/Doom/PROVENANCE.json">Source and asset provenance</a><br>Complete original shareware archive and engine sources accompany the firmware delivery. XZ decompression runs in your browser; bundled xzwasm, xz-embedded and walloc retain their author and licence notices.</footer>'''+index[end:]
 (runtime/'index.html').write_text(index,encoding='utf-8')
 # Keep upstream attribution verbatim in the external bundle; give the current
 # runtime accurate facts without claiming exact source/binary equivalence.
 shutil.copyfile(runtime/'upstream-engine.txt',sidecar/'upstream-engine-v1.txt')
 (runtime/'upstream-engine.txt').write_text('Chocolate Doom 3.0.0 / Cloudflare-derived WebAssembly engine.\nSource commit: 65e0d3ae2ffa604155eebd96ed40da6567bd08f4.\nBinary provider commit: e892222b66fd943bf196f285292aa15b98d89a5b.\nQualified OPL patch retains music. Exact source/binary reconstruction remains unproved.\nEngine sources, complete original Doom 1.9 shareware distribution and original attribution accompany this firmware delivery outside the router flash.\nNo runtime CDN or external game service is used.\n')
 inventory=[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p),'runtime_set':True} for p in sorted(runtime.iterdir())]
 package=parent|{'status':'COMPACT_RUNTIME_WITH_SEPARATE_PRESERVED_LOCAL_SOURCE_DELIVERY_BROWSER_UNRUN','inventory':inventory,'playable_set_bytes':sum(r['bytes'] for r in inventory),'full_preserved_package_bytes':sum(p.stat().st_size for p in runtime.iterdir())+sum(p.stat().st_size for p in sidecar.iterdir()),'source_bundle_files':[{'name':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(sidecar.iterdir())],'parent_package_sha256':sha(SOURCE/'package-result.json'),'original_archive_and_sources_retained':True}
 (OUT/'package-result.json').write_text(json.dumps(package,indent=2)+'\n')
 (OUT/'DELIVERY.md').write_text('# Doom XZ delivery\n\nwww/Doom contains the router runtime. source-and-original contains the complete original DOS distribution and the engine source archive; keep it with a firmware release. Original attribution and patched engine source files are preserved. Runtime download links refer only to files present on the router. No original inputs were deleted.\n\nThe WASM and WAD are unchanged. Engine source/binary reconstruction is not independently established. This is a packaging candidate; no HGW installation or firmware flash fit is implied.\n')
 print(json.dumps({'status':package['status'],'playable_set_bytes':package['playable_set_bytes'],'sidecar_bytes':sum(p.stat().st_size for p in sidecar.iterdir()),'output':str(OUT)}))
if __name__=='__main__':main()
