"""Compile F344 userspace objects without executing any native transport."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'outputs/preflight'/('f344-native-compile-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 src=ROOT/'work/kernel-port/f344';units=('f344_process','f344_profile','f344_probe','f344_backend','f344_transaction')
 script='set -eu\n'+''.join(f"cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -I'{linux(src)}' -c '{linux(src/(n+'.c'))}' -o '{linux(out/(n+'.o'))}'\n" for n in units)
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True,text=True,timeout=30)
 result={'status':'COMPILE_PASS_NOT_EXECUTED' if not p.returncode else 'FAIL','stderr':p.stderr,'hardware':False};(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return bool(p.returncode)
if __name__=='__main__':raise SystemExit(main())
