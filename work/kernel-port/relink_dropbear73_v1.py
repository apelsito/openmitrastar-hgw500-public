"""Fix PIE start-file selection, retaining every compiled Dropbear function."""
from pathlib import Path
import hashlib,json,os,re,shlex,subprocess
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OLD=BASE/'dropbear2026-arc750-v1';OUT=BASE/'dropbear73-pie-qualified-v1'
TC=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
SYSROOT=BASE/'libc2026-qualified-v4/sysroot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 OUT.mkdir(mode=0o700)
 original=next(l for l in (OLD/'build.log').read_text().splitlines() if ' -o dropbearmulti ' in l)
 cmd=shlex.split(original)
 assert '-Wl,-pie' in cmd and '-pie' not in cmd
 cmd=[('-pie' if x=='-Wl,-pie' else '--sysroot='+str(SYSROOT) if x.startswith('--sysroot=') else x) for x in cmd]
 pins={str(p):sha(p) for p in (OLD/'source/obj').glob('*.o')}
 pins.update({str(OLD/'source/libtomcrypt/libtomcrypt.a'):sha(OLD/'source/libtomcrypt/libtomcrypt.a'),str(OLD/'source/libtommath/libtommath.a'):sha(OLD/'source/libtommath/libtommath.a')})
 (OUT/'INPUT_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 lanes=[]
 for lane in ['a','b']:
  target=OUT/('dropbearmulti-'+lane);command=list(cmd);command[command.index('-o')+1]=str(target)
  (OUT/('command-'+lane+'.json')).write_text(json.dumps(command,indent=2)+'\n')
  with (OUT/('link-'+lane+'.log')).open('xb') as log:subprocess.run(command,cwd=OLD/'source',stdout=log,stderr=subprocess.STDOUT,check=True,timeout=90)
  subprocess.run([TC+'strip','--strip-unneeded',str(target)],check=True)
  dynamic=subprocess.check_output([TC+'readelf','-d',str(target)],text=True)
  assert 'TEXTREL' not in dynamic
  reloc=subprocess.check_output([TC+'readelf','-r',str(target)],text=True)
  # The relative fast path handles data words; no startup instruction literal
  # is allowed to receive a plain R_ARC_RELATIVE at an unaligned address.
  relative=[int(l.split()[0],16) for l in reloc.splitlines() if 'R_ARC_RELATIVE' in l]
  assert all(x%4==0 for x in relative),relative[:20]
  asm=subprocess.check_output([TC+'objdump','-d',str(target)],text=True)
  assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
  lanes.append({'lane':lane,'bytes':target.stat().st_size,'sha256':sha(target),'relative_relocations':len(relative),'relative_all_word_aligned':True,'textrel':False})
 assert lanes[0]['sha256']==lanes[1]['sha256']
 for file,h in pins.items():assert sha(Path(file))==h
 result={'status':'PASS_PAIRED_PIE_LINK_NO_UNALIGNED_RELATIVE','lanes':lanes,'change':'Replace linker-only -Wl,-pie with compiler-driver -pie to select qualified Scrt1/crtbeginS and current sysroot','parent_sha256':sha(OLD/'dropbearmulti'),'source_functions_reused_exact':True,'input_object_pins':len(pins),'hardware_accessed':False,'physical':'UNRUN','legacy_crypto':'unchanged modern key-only profile'}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
