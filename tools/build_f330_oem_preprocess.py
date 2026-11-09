"""Build F330 preprocessor library and execute original math in isolated QEMU."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,subprocess
from f328_oem_classifier_projection import require
from f328_eu_profile import derive
from f330_oem_preprocess_projection import emit
from f330_vectors import CASES,input_hash
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f330_oem_preprocess'
PRIVATE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):p=p.resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def parse(serial):
    results={};order=[];done=None;begins=0
    for line in serial.splitlines():
        if line.startswith('F330_CASE '):
            bits=dict(item.split('=') for item in line.split()[1:]);name=bits.pop('id')
            require(name not in results,'duplicate case')
            results[name]={k:int(v,16) for k,v in bits.items()};results[name]['pulses']=[];results[name]['zc_sources']=[];order.append(name)
        elif line.startswith('F330_PULSE ') or line.startswith('F330_SOURCE '):
            bits=dict(item.split('=') for item in line.split()[1:]);name=bits.pop('id');require(name in results,'uncorrelated row')
            target='pulses' if line.startswith('F330_PULSE') else 'zc_sources';results[name][target].append({k:int(v,16) for k,v in bits.items()})
        elif line.startswith('F330_ORACLE_DONE '):
            require(done is None,'duplicate done');done=dict(item.split('=') for item in line.split()[1:])
        elif line=='F330_ORACLE_BEGIN original_math=1 actual_hardware=0':
            begins+=1;require(begins==1 and not order,'duplicate or late begin')
        else:raise ValueError('unexpected serial output '+line)
    require(begins==1 or not serial,'missing begin')
    return results,order,done
def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=PRIVATE/('f330-preprocess-'+stamp);out.mkdir(parents=True,exist_ok=False)
    snapshot=out/'source';snapshot.mkdir()
    for p in SOURCE.iterdir():
        if p.is_file():(snapshot/p.name).write_bytes(p.read_bytes())
    projection=emit(out);profile=derive(out)
    (out/'qemu-only.ld').write_text('ENTRY(_start)\nSECTIONS { . = 0x80000000; .text : { *(.text.entry) *(.text) *(.text.*) } .rodata : { *(.rodata) *(.rodata.*) } .data : { *(.data) *(.data.*) } .bss : { *(.bss) *(.bss.*) *(COMMON) } /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }\n')
    tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');q=shlex.quote
    script=f'''set -eu
out={q(linux(out))}
src={q(linux(snapshot))}
tc={q(tc)}
for lane in a b; do
 "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -I"$out" -c "$src/f330_preprocess.c" -o "$out/core-$lane.o"
done
cmp "$out/core-a.o" "$out/core-b.o"
"${{tc}}ld" -r -o "$out/f330-preprocess.o" "$out/core-a.o" "$out/f330-oem-preprocess.o"
"${{tc}}nm" -u "$out/f330-preprocess.o" > "$out/undefined.txt"
test ! -s "$out/undefined.txt"
"${{tc}}ar" rcsD "$out/libf330-preprocess.a" "$out/f330-preprocess.o"
"${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -DF330_TEST -I"$out" -c "$src/f330_preprocess.c" -o "$out/test-core.o"
"${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -DF330_TEST -I"$out" -c "$src/f330_qemu_harness.c" -o "$out/harness.o"
"${{tc}}gcc" -c "$src/f330_qemu_entry.S" -o "$out/entry.o"
"${{tc}}ld" -T "$out/qemu-only.ld" -o "$out/qemu-only.elf" "$out/entry.o" "$out/harness.o" "$out/test-core.o" "$out/f330-oem-preprocess.o"
"${{tc}}objdump" -dr "$out/qemu-only.elf" > "$out/disassembly.txt"
test "$(sha256sum /home/user/qemu-arc-legacy-build/qemu-system-arc | cut -d' ' -f1)" = eb0ca3b68d859999d5132dd684eee490c32222d265378302b7c6c1f7d5c2cf94
set +e
timeout 45s /home/user/qemu-arc-legacy-build/qemu-system-arc -M arc-sim -cpu arc700,has-mpu=false -m 256M -display none -monitor none -no-reboot -nic none -serial stdio -d guest_errors -D "$out/guest-errors.log" -kernel "$out/qemu-only.elf" < /dev/null > "$out/serial.log" 2> "$out/qemu.stderr"
f330_rc=$?
printf '%s\\n' "$f330_rc" > "$out/qemu-exit.txt"
exit 0
'''
    (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=70)
    (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr)
    serial=(out/'serial.log').read_text(errors='replace') if (out/'serial.log').exists() else ''
    rows,order,done=parse(serial);errors=[]
    if p.returncode:errors.append('build failed')
    if not (out/'qemu-exit.txt').exists() or (out/'qemu-exit.txt').read_text().strip()!='0':errors.append('QEMU guest shutdown exit0 required')
    for name in ('guest-errors.log','qemu.stderr'):
        if not (out/name).exists() or (out/name).stat().st_size:errors.append(name+' not empty')
    expected=['history_a','history_b','history_c','history_empty','history_flush','cross_a','cross_b','merge','filters','tag_replace','terminal_tag_disabled','epoch','wrap_merge','limit_a','limit_b','quiet_100','quiet_101','pending_blocked','confirmed_epoch','busy_160','busy_161','failed_backend_blocked','oversize_refused','stale_refused']
    if order!=expected:errors.append('case identity/order mismatch')
    if done!={'cases':'00000018','failures':'00000000','actual_hardware':'0'}:errors.append('harness did not accept all24cases')
    for name,row in rows.items():
        if len(row['pulses'])!=row['total'] or len(row['zc_sources'])!=row['current']:errors.append('missing correlated output '+name)
        if [r['row'] for r in row['pulses']]!=list(range(row['total'])) or [r['row'] for r in row['zc_sources']]!=list(range(row['current'])):errors.append('duplicate/out-of-order row '+name)
        if row.get('fault')!=0 or row.get('guards')!=1:errors.append('fault or damaged canary '+name)
        fixture=CASES.get(name)
        if row.get('input_count')!=(129 if fixture is None else len(fixture)) or row.get('input_hash')!=input_hash(fixture):errors.append('raw fixture mismatch '+name)
        row['raw_input']=fixture
    result={'schema':'openmitrastar.f330-preprocess-oracle/v1','created_at':datetime.now(timezone.utc).isoformat(),
            'status':'PASS_ORIGINAL_PREPROCESS_QEMU_NO_HARDWARE' if not errors else 'INCOMPLETE_OR_FAILED',
            'errors':errors,'directory':str(out),'cases':rows,'case_order':order,'done':done,
            'projection':projection,'profile_sha256':profile['cfg_sha256'],'physical_hardware':False,'firmware':False,
            'library':{'path':str(out/'libf330-preprocess.a'),'sha256':sha(out/'libf330-preprocess.a') if (out/'libf330-preprocess.a').exists() else None},
            'files':{f.name:{'bytes':f.stat().st_size,'sha256':sha(f)} for f in out.iterdir() if f.is_file()}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'errors':errors,'path':str(out/'result.json'),'done':done,'stderr':p.stderr.decode(errors='replace')[-2000:]},indent=2))
    return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(main())
