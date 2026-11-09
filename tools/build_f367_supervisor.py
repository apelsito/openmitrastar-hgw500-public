"""Build only the F367 long-session/fresh-health supervisor delta twice."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/versions/f367-supervisor'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 out=ROOT/'outputs/kernel-port'/('f367-supervisor-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);shutil.copytree(SOURCE,out/'source')
 require_support='bd9b2f1158fcd84276edf8ec2766ce741301a8d27c88dca080e415fe62605fd7';assert sha(SOURCE/'f367_wdt_support.inc')==require_support
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic "$out/source/test_policy.c" -o "$out/policy-test"
"$out/policy-test" > "$out/policy-tests.log"
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-function -pedantic -DF340_TEST "$out/source/f367_supervisor.c" -o "$out/supervisor-test"
python3 {q(linux(ROOT/'tools/test_f367_supervisor_ipc.py'))} --binary "$out/supervisor-test" --result "$out/process-tests.json" > "$out/process-tests.stdout" 2> "$out/process-tests.stderr"
for lane in a b; do
 "${{tc}}gcc" --sysroot=/home/user/openmitrastar-uclibc-noatomic-sysroot -std=c11 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wno-unused-function -pedantic -static -Wl,--gc-sections "$out/source/f367_supervisor.c" -o "$out/om-watchdog-supervisor-f367-$lane"
 "${{tc}}strip" --strip-unneeded "$out/om-watchdog-supervisor-f367-$lane"
done
cmp "$out/om-watchdog-supervisor-f367-a" "$out/om-watchdog-supervisor-f367-b"
"${{tc}}objdump" -d "$out/om-watchdog-supervisor-f367-a" > "$out/disassembly.txt"
if grep -Eq '\\b(llock|scond)\\b' "$out/disassembly.txt"; then exit 1; fi
'''
 (out/'build.sh').write_bytes(script.encode());run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True,timeout=120)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr)
 binary=out/'om-watchdog-supervisor-f367-a';tests=json.loads((out/'process-tests.json').read_text()) if (out/'process-tests.json').exists() else {}
 passed=run.returncode==0 and tests.get('passed') is True
 report=dict(schema='openmitrastar.f367-supervisor-build/v1',status='PASS_OFFLINE_F367_SUPERVISOR' if passed else 'FAIL',reproducible=passed,
  artifact=dict(path=str(binary),sha256=sha(binary),bytes=binary.stat().st_size) if binary.exists() else None,
  runtime_path='/usr/sbin/om-watchdog-supervisor-f367',wire_version=2,response_bytes=190,json_schema='openmitrastar.f367-supervisor-state/v1',
  total_budget_max_ms=5400000,phase_budget_max_ms=60000,health_lease_ms=5000,phase_sequence_max=128,
  watchdog_support_unchanged_sha256=require_support,owner_namespace='/run/openmitrastar/watchdog',kernel_version='#358 @1790006400',
  policy_tests=(out/'policy-tests.log').read_text().strip() if (out/'policy-tests.log').exists() else '',process_tests=tests,
  sources={str(p.resolve()):sha(p) for p in [*SOURCE.iterdir(),Path(__file__),ROOT/'tools/test_f367_supervisor_ipc.py'] if p.is_file()},hardware_actions=False)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),status=report['status'],stderr=run.stderr.decode(errors='replace')[-2000:])));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
