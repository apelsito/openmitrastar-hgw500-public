"""Compile and test F336 userspace probe without opening a real watchdog."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,shlex,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):p=p.resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
    out=ROOT/'outputs/kernel-port'/('f336-wdt-probe-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'work/kernel-port/versions/f336-wdt-ram/f336_wdt_probe.c';shutil.copy2(source,out/source.name)
    shutil.copy2(ROOT/'tools/test_f336_wdt_probe.py',out/'test_f336_wdt_probe.py');q=shlex.quote
    tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -DF336_TEST "$out/f336_wdt_probe.c" -o "$out/probe-test"
python3 "$out/test_f336_wdt_probe.py" --binary "$out/probe-test" --result "$out/tests.json" > "$out/tests.stdout" 2> "$out/tests.stderr"
for lane in a b; do
 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=c11 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -Wall -Wextra -Werror -pedantic -static -Wl,--gc-sections "$out/f336_wdt_probe.c" -o "$out/f336-wdt-probe-$lane"
 "${{tc}}strip" --strip-unneeded "$out/f336-wdt-probe-$lane"
done
cmp "$out/f336-wdt-probe-a" "$out/f336-wdt-probe-b"
"${{tc}}objdump" -d "$out/f336-wdt-probe-a" > "$out/disassembly.txt"
! grep -Eq '\\b(llock|scond)\\b' "$out/disassembly.txt"
"${{tc}}readelf" -h -l "$out/f336-wdt-probe-a" > "$out/elf.txt"
'''
    (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=120)
    (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr)
    tests=json.loads((out/'tests.json').read_text()) if (out/'tests.json').exists() else {};binary=out/'f336-wdt-probe-a'
    report={'schema':'openmitrastar.f336-userspace-probe/v1','status':'PASS_OFFLINE_NO_WATCHDOG_OPEN' if not p.returncode and tests.get('passed') else 'FAIL','tests':tests,'hardware_actions':False,'source_sha256':sha(source),'artifact':{'path':str(binary),'bytes':binary.stat().st_size,'sha256':sha(binary)} if binary.exists() else None,'reproducible':not p.returncode}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'stderr':p.stderr.decode(errors='replace')[-2500:]},indent=2));return p.returncode
if __name__=='__main__':raise SystemExit(main())
