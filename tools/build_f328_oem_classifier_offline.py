"""Build and run exact-classifier synthetic vectors exclusively in local QEMU."""
from pathlib import Path
import hashlib,json,re,shlex,subprocess
from datetime import datetime,timezone
import f328_oem_classifier_projection as projection
from f328_eu_profile import derive
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/modules/f328_oem_classifier'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def linux(path):
    path=path.resolve();return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def validate_run(out):
    errors=[]
    rc=(out/'qemu-exit.txt').read_text().strip() if (out/'qemu-exit.txt').exists() else 'missing'
    if rc!='0':errors.append('QEMU must exit 0 via intentional flag1 guest shutdown; timeout/crash refused')
    for name in ('guest-errors.log','qemu.stderr'):
        if not (out/name).is_file() or (out/name).stat().st_size!=0:errors.append(name+' not empty/present')
    serial=(out/'serial.log').read_text(errors='replace') if (out/'serial.log').exists() else ''
    pattern=(r'F328_VECTOR count=([0-9a-f]{8}) pri=([0-9a-f]{8}) width=([0-9a-f]{8}) '
             r'detected=([0-9a-f]{8}) poll=([0-9a-f]{8}) ssr=([0-9a-f]{8}) '
             r'itlv=([0-9a-f]{8}) lsr=([0-9a-f]{8}) fault=([0-9a-f]{8}) guards=([0-9a-f]{8})')
    lines=serial.splitlines()
    if len(lines)!=8 or lines[:1]!=['F328_ORACLE_BEGIN exact_oem_classifier_only=1'] or lines[-1:]!=['F328_ORACLE_DONE vectors=6 rf_proof=0 firmware=0']:
        errors.append('missing/duplicate/unexpected begin, result rows or completion')
    expected=[(2,10000,40,0),(8,10000,40,1),(16,10000,40,1),
              (32,10000,40,1),(32,10000,1,0),(32,10000,500,0)]
    rows=[]
    for index,line in enumerate(lines[1:-1]):
        m=re.fullmatch(pattern,line)
        if not m:errors.append('invalid vector row '+str(index));continue
        values=tuple(int(v,16) for v in m.groups());rows.append(values)
        if index>=len(expected) or values!=(expected[index]+(0,expected[index][3],0,0,0,1)):
            errors.append('unexpected classifier/counter/fault/guard result '+str(index))
    if len(rows)!=6:errors.append('exact six correlated vectors required')
    return {'passed':not errors,'qemu_exit':rc,'rows':rows,'errors':errors,
            'termination':'flag1 after harness returns -> QEMU GUEST_SHUTDOWN -> exit0; timeout124 is failure'}
def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=BASE/('f328-oem-classifier-'+stamp);out.mkdir(parents=True,exist_ok=False)
    snapshot=out/'source';snapshot.mkdir()
    for p in SRC.iterdir():
        if p.is_file(): (snapshot/p.name).write_bytes(p.read_bytes())
    projection.emit(out);profile=derive(out)
    linker='''ENTRY(_start)
SECTIONS {
 . = 0x80000000;
 .text : { *(.text.entry) *(.text) *(.text.*) }
 .rodata : { *(.rodata) *(.rodata.*) }
 .data : { *(.data) *(.data.*) }
 .bss : { *(.bss) *(.bss.*) *(COMMON) }
 /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
'''
    (out/'qemu-only.ld').write_text(linker)
    q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    script=f'''set -eu
out={q(linux(out))}
src={q(linux(snapshot))}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -DF328_ABI_TEST -fno-builtin "$src/f328_legacy_abi.c" "$src/test_f328_legacy_abi.c" -o "$out/test-facade"
"$out/test-facade" > "$out/facade-tests.txt"
for lane in a b; do
 "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -c "$src/f328_legacy_abi.c" -o "$out/abi-$lane.o"
done
cmp "$out/abi-a.o" "$out/abi-b.o"
"${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -I"$out" -c "$src/f328_qemu_harness.c" -o "$out/harness.o"
"${{tc}}gcc" -c "$src/f328_qemu_entry.S" -o "$out/entry.o"
"${{tc}}ld" -r -o "$out/classifier-with-abi.o" "$out/f328-oem-classifier.o" "$out/abi-a.o"
"${{tc}}nm" -u "$out/classifier-with-abi.o" > "$out/undefined.txt"
test ! -s "$out/undefined.txt"
"${{tc}}ld" -T "$out/qemu-only.ld" -o "$out/qemu-only.elf" "$out/entry.o" "$out/harness.o" "$out/classifier-with-abi.o"
"${{tc}}readelf" -h -r "$out/qemu-only.elf" > "$out/executable-contract.txt"
"${{tc}}objdump" -dr "$out/qemu-only.elf" > "$out/executable-disassembly.txt"
sha256sum /home/user/qemu-arc-legacy-build/qemu-system-arc > "$out/qemu-sha256.txt"
/home/user/qemu-arc-legacy-build/qemu-system-arc --version > "$out/qemu-version.txt"
set +e
timeout 8s /home/user/qemu-arc-legacy-build/qemu-system-arc -M arc-sim -cpu arc700,has-mpu=false -m 256M -display none -monitor none -no-reboot -nic none -serial stdio -d guest_errors -D "$out/guest-errors.log" -kernel "$out/qemu-only.elf" < /dev/null > "$out/serial.log" 2> "$out/qemu.stderr"
f328_qemu_rc=$?
printf '%s\\n' "$f328_qemu_rc" > "$out/qemu-exit.txt"
exit 0
'''
    (out/'build.sh').write_bytes(script.encode('utf-8'))
    result=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=70)
    (out/'build.stdout').write_bytes(result.stdout);(out/'build.stderr').write_bytes(result.stderr)
    serial=(out/'serial.log').read_text(errors='replace') if (out/'serial.log').exists() else ''
    acceptance=validate_run(out)
    passed=result.returncode==0 and acceptance['passed']
    report={'schema':'openmitrastar.f328-private-oem-oracle/v1','created_at':datetime.now(timezone.utc).isoformat(),
            'status':'PASS_EXACT_CLASSIFIER_SYNTHETIC_QEMU' if passed else 'INCOMPLETE_QEMU_OR_BUILD',
            'build_returncode':result.returncode,'acceptance':acceptance,'directory':str(out),'original_oem_sha256':projection.EXPECTED,
            'profile_sha256':profile['cfg_sha256'],'physical_proof':False,'linux510_module_acceptance':False,
            'firmware_created':False,'hardware_actions':False,
            'artifacts':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'serial':serial[-2500:],'stderr':result.stderr.decode(errors='replace')[-1200:]},indent=2))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
