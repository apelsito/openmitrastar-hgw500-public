"""Build/test F344 native mode workflow without opening any device transport."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,subprocess
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'work/kernel-port/f344';VENDOR=ROOT/'work/sources/Quantenna-GPL/buildroot/package/zhostapd/hostapd-git/src'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=ROOT/'outputs/userspace'/('f344-mode-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);(out/'source').mkdir()
 units=['f344_process.c','f344_profile.c','f344_probe.c','f344_backend.c','f344_transaction.c','f344_native.h','f344_transaction.h','f344_mode_gate.h','test_native.c']
 for n in units:(out/'source'/n).write_bytes((SOURCE/n).read_bytes())
 (out/'source/sha256-internal.c').write_bytes((VENDOR/'crypto/sha256-internal.c').read_bytes())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');flags=f'-DNO_SHA256_WRAPPER -I{q(linux(VENDOR/"utils"))} -I{q(linux(VENDOR/"crypto"))}';src=q(linux(out/'source'))
 script=f'''set -eu
out={q(linux(out))}
src={src}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra {flags} "$src/f344_process.c" "$src/f344_profile.c" "$src/test_native.c" "$src/sha256-internal.c" -Wl,--wrap=clock_gettime -o "$out/native-tests"
"$out/native-tests"
for lane in a b; do
 mkdir "$out/$lane"
 "$tc"gcc --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -mno-atomic -std=c11 -O2 -Wall -Wextra -static {flags} -ffile-prefix-map="$out=/f344-mode" "$src/f344_process.c" "$src/f344_profile.c" "$src/f344_probe.c" "$src/f344_backend.c" "$src/f344_transaction.c" "$src/sha256-internal.c" -o "$out/$lane/om-f344-mode"
done
cmp "$out/a/om-f344-mode" "$out/b/om-f344-mode"
"$tc"objdump -d "$out/a/om-f344-mode" > "$out/arc-disassembly.txt"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True,text=True,timeout=90)
 errors=[];artifact={}
 if p.returncode:errors.append('native tests or ARC build failed')
 else:
  path=out/'a/om-f344-mode'
  with path.open('rb') as f:
   e=ELFFile(f)
   if e['e_machine']!='EM_ARC_COMPACT':errors.append('wrong ARC machine')
   if e.get_section_by_name('.dynamic'):errors.append('unexpected dynamic dependency')
  import re
  if re.search(r'\b(?:llock|scond)(?:\.[a-z]+)?\b',(out/'arc-disassembly.txt').read_text()):errors.append('unsupported atomic instructions')
  artifact={'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}
 result={'schema':'openmitrastar.f344-native/v1','status':'PASS_NATIVE_PROCESS_PROFILE_AND_REPRODUCIBLE_ARC_BUILD' if not errors else 'FAIL','errors':errors,'stdout':p.stdout,'stderr':p.stderr,'artifact':artifact,'sources':{str(v.relative_to(out/'source')):sha(v) for v in (out/'source').iterdir()},'hardware':False,'arc_runtime':'UNRUN','wifi_physical':'USER_DEFERRED'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
