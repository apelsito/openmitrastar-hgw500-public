"""Execute actual F348 core + map_rom adapter with host RAM services only."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,re,shlex,subprocess
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/versions/f348-flash-arbitration'
BASE='/home/user/openmitrastar-build/f340-watchdog-20260921T132951Z/linux'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def linux(path):
    path=Path(path).resolve();return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:]
def function(text,name):
    m=re.search(r'^static int '+name+r'\([^;]+?\)\s*\{',text,re.M);assert m,name
    start=m.start();pos=m.end();depth=1
    while depth:
        if text[pos]=='{':depth+=1
        elif text[pos]=='}':depth-=1
        pos+=1
    return text[start:pos]
def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'outputs/preflight'/('f348-reader-tests-'+stamp);out.mkdir(parents=True,exist_ok=False)
    read=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cat',BASE+'/drivers/mtd/mtdchar.c'],capture_output=True,check=True)
    assert hashlib.sha256(read.stdout).hexdigest()=='3467dbaa76b809e2f4ba6bfec029ab654e9a298119a1c5e71a8db6d80ebc73ac'
    (out/'mtdchar.c').write_bytes(read.stdout)
    mapper=(SOURCE/'drivers/mtd/chips/map_rom.c').read_text()
    mapper=re.sub(r'^#include.*$','',mapper,flags=re.M)
    # Preserve the exact included core at the include location, not at EOF.
    anchor='EXPORT_SYMBOL_GPL(qtn_topaz_flash_claim);'
    mapper=mapper.replace(anchor,(SOURCE/'drivers/mtd/chips/qtn_topaz_flash_guard_core.inc').read_text()+'\n'+anchor)
    combined=(SOURCE/'tests/maprom_stubs.h').read_text()+'\n'+mapper+'\n'+function(read.stdout.decode(),'mtdchar_mmap')+'\n'+(SOURCE/'tests/maprom_main.inc').read_text()
    (out/'adapter.c').write_bytes(combined.encode())
    q=shlex.quote
    script=f'''set -eu
out={q(linux(out))}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -pthread {q(linux(SOURCE/'tests/test_flash_guard.c'))} -o "$out/core"
timeout 10s "$out/core" > "$out/core.log"
cc -std=gnu11 -O2 -Wall -Wextra -Werror -Wno-unused-parameter -pthread "$out/adapter.c" -o "$out/adapter"
timeout 10s "$out/adapter" > "$out/adapter.log"
cc -std=c11 -O0 -Wall -Wextra -Werror -pedantic -fanalyzer -pthread -c {q(linux(SOURCE/'tests/test_flash_guard.c'))} -o "$out/core-analyzer.o" > "$out/analyzer.log" 2>&1
'''
    (out/'test.sh').write_bytes(script.encode())
    run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'test.sh')],capture_output=True)
    (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr)
    result={'schema':'openmitrastar.f348-reader-tests/v1','status':'PASS' if run.returncode==0 else 'FAIL',
      'exit_code':run.returncode,'hardware_actions':False,'actual_core':True,'actual_maprom_probe':True,
      'actual_mtdchar_mmap':True,'context':'native C with fake ROM/MTD and real pthread mutex',
      'tests':{name:(out/name).read_text() for name in ['core.log','adapter.log','analyzer.log'] if (out/name).exists()},
      'sources':{str(p):sha(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()},'runner_sha256':sha(__file__)}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'result':str(out/'result.json')}));return run.returncode
if __name__=='__main__':raise SystemExit(main())
