"""Native execution of F350 provider/F342/NOR model and real kernel adapter bodies."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess,shutil
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/versions/f356-observe-ram/provider'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f356-provider-tests-'+stamp);out.mkdir(parents=True,exist_ok=False)
 shutil.copytree(SOURCE,out/'source')
 body=re.sub(r'^#include.*$','',(SOURCE/'f350_kernel.c').read_text(),flags=re.M)
 (out/'source/kernel_native.c').write_bytes(((SOURCE/'test_kernel_stubs.h').read_text()+'\n'+body+'\n'+(SOURCE/'test_kernel_main.inc').read_text()).encode())
 q=shlex.quote
 script=f'''set -eu
out={q(linux(out))}
cd "$out/source"
flags='-std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes'
gcc $flags -O2 f350_provider.c f342_journal.c f345_protocol.c test_f350_provider.c -o "$out/model"
timeout 30s "$out/model" > "$out/model.log"
gcc -std=gnu11 -Wall -Wextra -Werror -Wno-unused-parameter -pthread -O2 kernel_native.c f350_provider.c f342_journal.c f345_protocol.c -o "$out/adapter"
timeout 15s "$out/adapter" > "$out/adapter.log"
gcc $flags -fanalyzer -c f350_provider.c -o "$out/analyzer.o" > "$out/analyzer.log" 2>&1
'''
 (out/'test.sh').write_bytes(script.encode())
 r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'test.sh')],capture_output=True)
 (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
 report={'schema':'openmitrastar.f356-provider-tests/v1','status':'PASS' if not r.returncode else 'FAIL','exit_code':r.returncode,
  'hardware_actions':False,'simulation_only':True,'sources':{str(p):sha(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()},
  'logs':{n:(out/n).read_text() for n in ['model.log','adapter.log','analyzer.log'] if (out/n).exists()}}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'result':str(out/'result.json')}));return r.returncode
if __name__=='__main__':raise SystemExit(main())
