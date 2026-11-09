"""Single MIME-table fix and strip unallocated debug data; retain function code."""
from pathlib import Path
import hashlib,json,re,shlex,shutil,subprocess
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OLD=BASE/'modern-web-arc750-v1';OUT=BASE/'uhttpd73-wasm-mime-v1'
TC=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 OUT.mkdir(mode=0o700);source=OUT/'source';shutil.copytree(OLD/'sources/uhttpd',source)
 file=source/'mimetypes.h';text=file.read_text()
 assert '"application/wasm"' not in text
 text=text.replace('\t{ NULL, NULL }','\t{ "wasm", "application/wasm" },\n\t{ NULL, NULL }')
 file.write_text(text);config=(OLD/'build-uhttpd/CMakeFiles/uhttpd.dir/flags.make').read_text().splitlines()
 flags=[]
 for key in ['C_DEFINES','C_INCLUDES','C_FLAGS']:
  flags+=shlex.split(next(l.split(' = ',1)[1] for l in config if l.startswith(key+' = ')))
 flags=[x for x in flags if x!='-g3'];flags+=['--sysroot='+str(BASE/'libc2026-qualified-v4/sysroot')]
 link=shlex.split((OLD/'build-uhttpd/CMakeFiles/uhttpd.dir/link.txt').read_text())
 link=[x.replace('--sysroot='+str(BASE/'libc2026-qualified-v1/sysroot'),'--sysroot='+str(BASE/'libc2026-qualified-v4/sysroot')) for x in link]
 pins={str(f):sha(f) for f in (OLD/'build-uhttpd/CMakeFiles/uhttpd.dir').glob('*.o')}
 lanes=[]
 for lane in ['a','b']:
  folder=OUT/lane;folder.mkdir();obj=folder/'file.c.o'
  cmd=[TC+'gcc']+flags+['-I'+str(source),'-c',str(source/'file.c'),'-o',str(obj)]
  with (folder/'compile.log').open('xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
  command=[str(obj) if x=='CMakeFiles/uhttpd.dir/file.c.o' else x for x in link]
  command[command.index('-o')+1]=str(folder/'uhttpd')
  with (folder/'link.log').open('xb') as log:subprocess.run(command,cwd=OLD/'build-uhttpd',stdout=log,stderr=subprocess.STDOUT,check=True)
  subprocess.run([TC+'strip','--strip-unneeded',str(folder/'uhttpd')],check=True)
  binary=folder/'uhttpd';asm=subprocess.check_output([TC+'objdump','-d',str(binary)],text=True)
  assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
  lanes.append({'lane':lane,'bytes':binary.stat().st_size,'sha256':sha(binary)})
 assert lanes[0]['sha256']==lanes[1]['sha256']
 for p,h in pins.items():assert sha(Path(p))==h,p
 result={'status':'PASS_PAIRED_UHTTPD_WASM_MIME','lanes':lanes,'change':'Add application/wasm MIME; strip debug/symbol sections; every other source retained','mime_source_sha256':sha(file),'physical':'UNRUN','hardware_accessed':False}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
