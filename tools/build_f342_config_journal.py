"""F342 portable journal tests/analyzer/reproducible ARC archive. No hardware."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f342_config_journal'
BASE=ROOT/'work/kernel-port/modules/f318_store_transaction'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def require(test,reason):
    if not test:raise ValueError(reason)
def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/kernel-port'/('f342-config-journal-'+stamp);out.mkdir(exist_ok=False)
    files=[SOURCE/'f342_journal.c',SOURCE/'f342_journal.h',SOURCE/'test_f342_journal.c',BASE/'f318_store_transaction.h',BASE/'f318_store_transaction.c',Path(__file__).resolve()]
    pins={str(p):sha(p) for p in files};src=out/'sources';src.mkdir()
    for p in files:(src/p.name).write_bytes(p.read_bytes())
    core=(src/'f342_journal.c').read_text(encoding='ascii')
    require(not re.search(r'\b(?:ioremap|readl|writel|mtd_device_register|socket|popen|system)\s*\(',core),'nonportable operation')
    q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
    script=f'''set -eu
out={q(linux(out))}
src="$out/sources"
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -Wpedantic -I"$src" "$src/f342_journal.c" "$src/f318_store_transaction.c" "$src/test_f342_journal.c" -o "$out/test-journal"
"$out/test-journal" > "$out/tests.log" 2> "$out/tests.stderr"
cc -std=c11 -O0 -Wall -Wextra -Werror -Wpedantic -fanalyzer -I"$src" -c "$src/f342_journal.c" -o "$out/analyzer.o" > "$out/analyzer.log" 2>&1
if printf 'int main(void){{return 0;}}\\n' | cc -x c -fsanitize=address,undefined -o "$out/sanitizer-link-probe" - > "$out/sanitizer-link.stdout" 2> "$out/sanitizer-link.stderr"; then
 cc -std=c11 -O1 -g -Wall -Wextra -Werror -Wpedantic -fsanitize=address,undefined -fno-omit-frame-pointer -I"$src" "$src/f342_journal.c" "$src/f318_store_transaction.c" "$src/test_f342_journal.c" -o "$out/test-journal-sanitized"
 ASAN_OPTIONS=detect_leaks=1 "$out/test-journal-sanitized" > "$out/sanitized.log" 2> "$out/sanitized.stderr"
 printf 'PASS\\n' > "$out/sanitizer-status.txt"
else
 printf 'NOT_RUN_TOOLCHAIN_RUNTIME_UNAVAILABLE\\n' > "$out/sanitizer-status.txt"
fi
for lane in a b; do
 mkdir "$out/$lane"
 SOURCE_DATE_EPOCH=1790006400 "${{tc}}gcc" -std=c11 -Os -g0 -mno-atomic -fno-stack-protector -ffunction-sections -fdata-sections -fstack-usage -Wframe-larger-than=512 -Wall -Wextra -Werror -Wpedantic -I"$src" -c "$src/f342_journal.c" -o "$out/$lane/f342_journal.o"
 "${{tc}}ar" rcsD "$out/$lane/libf342journal.a" "$out/$lane/f342_journal.o"
done
cmp "$out/a/f342_journal.o" "$out/b/f342_journal.o"
cmp "$out/a/libf342journal.a" "$out/b/libf342journal.a"
"${{tc}}readelf" -h "$out/a/f342_journal.o" > "$out/elf.txt"
"${{tc}}nm" -u "$out/a/f342_journal.o" > "$out/undefined.txt"
"${{tc}}size" "$out/a/f342_journal.o" > "$out/size.txt"
'''
    (out/'build.sh').write_text(script,encoding='ascii',newline='\n');print(json.dumps(dict(started=str(out),hardware_actions=False)),flush=True)
    run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
    (out/'launcher.stdout').write_bytes(run.stdout);(out/'launcher.stderr').write_bytes(run.stderr)
    result=dict(schema='openmitrastar.f342-config-journal/v1',status='BUILD_FAILED',returncode=run.returncode,source_pins=pins,hardware_actions=False,mmio_backend='ABSENT',firmware_created=False,persistent_writes_enabled=False)
    if not run.returncode:
        match=re.fullmatch(r'PASS F342 checks=(\d+) faults=(\d+) power_cuts=(\d+) workspace=552 payload_max=4096 hardware=0\n',(out/'tests.log').read_text())
        require(match is not None,'test result contract')
        sanitizer_status=(out/'sanitizer-status.txt').read_text().strip()
        if sanitizer_status=='PASS':
            require((out/'tests.log').read_bytes()==(out/'sanitized.log').read_bytes(),'sanitized outcome differs')
            require(not (out/'sanitized.stderr').read_bytes(),'sanitizer diagnostics')
        else:require(sanitizer_status=='NOT_RUN_TOOLCHAIN_RUNTIME_UNAVAILABLE','unknown sanitizer state')
        require(not (out/'tests.stderr').read_bytes() and not (out/'analyzer.log').read_bytes(),'diagnostic warnings/errors')
        require('ARC' in (out/'elf.txt').read_text(),'wrong archive architecture')
        undefined={line.split()[-1] for line in (out/'undefined.txt').read_text().splitlines() if line.split()}
        require(undefined<= {'memcpy','memcmp','memset'},'unexpected external dependency')
        stack=[]
        for line in (out/'a/f342_journal.su').read_text().splitlines():
            fields=line.split('\t');stack.append({'function':fields[0].rsplit(':',1)[-1],'bytes':int(fields[1]),'kind':fields[2]})
        require(all(s['bytes']<=512 and s['kind']=='static' for s in stack),'unbounded/large ARC frame')
        artifact=out/'a/libf342journal.a';result.update(status='PASS_OFFLINE_PORTABLE_JOURNAL',checks=int(match[1]),faults=int(match[2]),power_cut_snapshots=int(match[3]),workspace_bytes=552,
            gcc_analyzer_pass=True,sanitizers_pass=True if sanitizer_status=='PASS' else None,sanitizers_status=sanitizer_status,arc_reproducible=True,arc_stack=stack,undefined=sorted(undefined),
            artifact={'path':str(artifact),'bytes':artifact.stat().st_size,'sha256':sha(artifact)},
            scope={'slots':['0x00dc0000','0x00dd0000'],'erase_bytes':65536,'payload_max':4096,'page_bytes':256,'sequence_bits':64,'commit_last':True,'load_read_only':True})
    require(all(sha(p)==h for p,h in pins.items()),'input changed during build')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii');print(json.dumps({'result':str(out/'result.json'),'status':result['status']},indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
