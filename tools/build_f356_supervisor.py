"""Build/test F340's single-owner supervisor; no real watchdog is opened."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 assert shutil.disk_usage('C:/').free>500*1024*1024
 out=ROOT/'outputs/kernel-port'/('f356-supervisor-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 source=ROOT/'work/kernel-port/versions/f356-observe-ram/supervisor';shutil.copytree(source,out/'source');shutil.copy2(ROOT/'tools/test_f356_supervisor.py',out/'test_f356_supervisor.py')
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic "$out/source/test_policy.c" -o "$out/policy-test"
"$out/policy-test" > "$out/policy-tests.log"
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-function -pedantic -DF340_TEST "$out/source/f356_supervisor.c" -o "$out/supervisor-test"
python3 "$out/test_f356_supervisor.py" --binary "$out/supervisor-test" --result "$out/process-tests.json" > "$out/process-tests.stdout" 2> "$out/process-tests.stderr"
cc -std=c11 -O0 -Wall -Wextra -Werror -Wno-unused-function -pedantic -fanalyzer -DF340_TEST "$out/source/f356_supervisor.c" -o "$out/analyzer-test" > "$out/analyzer.log" 2>&1
for lane in a b; do
 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=c11 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wno-unused-function -pedantic -static -Wl,--gc-sections "$out/source/f356_supervisor.c" -o "$out/om-watchdog-supervisor-f356-$lane"
 "${{tc}}strip" --strip-unneeded "$out/om-watchdog-supervisor-f356-$lane"
done
cmp "$out/om-watchdog-supervisor-f356-a" "$out/om-watchdog-supervisor-f356-b"
"${{tc}}objdump" -d "$out/om-watchdog-supervisor-f356-a" > "$out/disassembly.txt"
if grep -Eq '\\b(llock|scond)\\b' "$out/disassembly.txt"; then exit 1; fi
"${{tc}}readelf" -h -l "$out/om-watchdog-supervisor-f356-a" > "$out/elf.txt"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
 (out/'stdout.log').write_bytes(p.stdout);(out/'stderr.log').write_bytes(p.stderr)
 binary=out/'om-watchdog-supervisor-f356-a';tests=json.loads((out/'process-tests.json').read_text()) if (out/'process-tests.json').exists() else {}
 good=p.returncode==0 and tests.get('passed') and b'F340_TEST' not in binary.read_bytes()
 report={'schema':'openmitrastar.f356-supervisor-build/v1','status':'PASS_OFFLINE_SUPERVISOR' if good else 'FAIL',
  'hardware_actions':False,'automatic_arm':False,'default_invocation':'inspect-only-no-watchdog-open',
  'policy_tests':(out/'policy-tests.log').read_text().strip() if (out/'policy-tests.log').exists() else '',
  'process_tests':tests,'analyzer':'PASS' if not p.returncode else 'UNQUALIFIED','reproducible':bool(good),
  'artifact':{'path':str(binary),'bytes':binary.stat().st_size,'sha256':sha(binary)} if binary.exists() else None,
  'sources':{str(f.relative_to(ROOT)):sha(f) for f in sorted(source.iterdir()) if f.is_file()}}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'stderr':p.stderr.decode(errors='replace')[-2000:]}));return 0 if good else 1
if __name__=='__main__':raise SystemExit(main())
