"""Build portable F333 and compare against original loops in private QEMU."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shlex,subprocess
from f328_oem_classifier_projection import require
from f333_acquisition_oracle import emit
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f333_acquisition'
PRIVATE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):p=p.resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--suite',choices=['full','raw','zc'],default='full');args=parser.parse_args()
    out=PRIVATE/('f333-acquisition-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
    source=out/'source';source.mkdir()
    for p in SOURCE.iterdir():
        if p.is_file():(source/p.name).write_bytes(p.read_bytes())
    slices=emit(out)
    linker='''ENTRY(_start)
SECTIONS { . = 0x80000000; .text : { *(.text.entry) *(.text) *(.text.*) }
 .rodata : { *(.rodata) *(.rodata.*) } .data : { *(.data) *(.data.*) }
 .bss : { *(.bss) *(.bss.*) *(COMMON) } /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
 f333_negative_low = -ABSOLUTE(f333_low_bank); f333_negative_high = -ABSOLUTE(f333_high_bank);
 f333_negative_zc = -ABSOLUTE(f333_zc_ram); f333_zc_valid_end = f333_zc_ram+0xdff; f333_zc_end = f333_zc_ram+0xfff;
}
'''
    (out/'qemu-only.ld').write_text(linker)
    q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    suite_flags='-DF333_SKIP_RAW' if args.suite=='zc' else '-DF333_SKIP_ZC' if args.suite=='raw' else ''
    script=f'''set -eu
out={q(linux(out))}
src={q(linux(source))}
tc={q(tc)}
cd "$out"
for lane in a b; do
 "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls -c "$src/f333_acquisition.c" -o "$out/core-$lane.o"
done
cmp "$out/core-a.o" "$out/core-b.o"
"${{tc}}ar" rcsD "$out/libf333-acquisition.a" "$out/core-a.o"
"${{tc}}nm" -u "$out/core-a.o" > "$out/undefined.txt"
test ! -s "$out/undefined.txt"
 "${{tc}}gcc" -std=c11 -Os -Wall -Wextra -Werror -pedantic -ffreestanding -fno-builtin -fno-common -mno-sdata -mlong-calls {suite_flags} -c "$src/f333_qemu_harness.c" -o "$out/harness.o"
"${{tc}}gcc" -c "$src/f333_qemu_entry.S" -o "$out/entry.o"
"${{tc}}gcc" -c "$out/oracle.S" -o "$out/oracle.o"
"${{tc}}ld" -T "$out/qemu-only.ld" -o "$out/qemu-only.elf" "$out/entry.o" "$out/harness.o" "$out/core-a.o" "$out/oracle.o"
"${{tc}}objdump" -dr "$out/qemu-only.elf" > "$out/disassembly.txt"
"${{tc}}nm" "$out/qemu-only.elf" > "$out/symbols.txt"
for pair in 'f333_negative_high f333_high_bank' 'f333_negative_low f333_low_bank' 'f333_negative_zc f333_zc_ram'; do
 set -- $pair
 neg=$(awk -v key="$1" '$3==key {{print "0x"$1}}' "$out/symbols.txt")
 base=$(awk -v key="$2" '$3==key {{print "0x"$1}}' "$out/symbols.txt")
 test $(((neg+base)&0xffffffff)) -eq 0
done
raw_body=$(awk '$3=="f333_raw_body" {{print "0x"$1}}' "$out/symbols.txt")
zc_body=$(awk '$3=="f333_zc_body" {{print "0x"$1}}' "$out/symbols.txt")
test $((raw_body&3)) -eq 0
test $((zc_body&3)) -eq 2
printf '%s\\n' 'PASS negative aliases and original ARC instruction phase' > "$out/binding.txt"
test "$(sha256sum /home/user/qemu-arc-legacy-build/qemu-system-arc | cut -d' ' -f1)" = eb0ca3b68d859999d5132dd684eee490c32222d265378302b7c6c1f7d5c2cf94
set +e
timeout 45s /home/user/qemu-arc-legacy-build/qemu-system-arc -M arc-sim -cpu arc700,has-mpu=false -m 256M -display none -monitor none -no-reboot -nic none -serial stdio -d guest_errors -D "$out/guest-errors.log" -kernel "$out/qemu-only.elf" < /dev/null > "$out/serial.log" 2> "$out/qemu.stderr"
f333_rc=$?
printf '%s\\n' "$f333_rc" > "$out/qemu-exit.txt"
exit 0
'''
    (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=70)
    (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr)
    serial=(out/'serial.log').read_text(errors='replace') if (out/'serial.log').exists() else ''
    prefix='F333_ORACLE_BEGIN original_loops=1 hardware=0\n'
    if args.suite!='zc':prefix+='F333_FIRST_RAW_DONE\nF333_METADATA_DONE\nF333_RAW_PLANS_DONE\n'
    if args.suite!='raw':prefix+='F333_FIRST_ZC_DONE\n'
    pattern=re.escape(prefix)+(r'F333_ORACLE_DONE raw_cases=([0-9a-f]{8}) zc_cases=([0-9a-f]{8}) comparisons=([0-9a-f]{8}) sample_comparisons=([0-9a-f]{8}) failures=([0-9a-f]{8}) first_failure=([0-9a-f]{8}) hardware=0\n')
    match=re.fullmatch(pattern,serial);values=[int(x,16) for x in match.groups()] if match else []
    errors=[]
    if p.returncode:errors.append('build failed')
    expected_raw=0 if args.suite=='zc' else 2368;expected_zc=0 if args.suite=='raw' else 320
    if not match or values[0]!=expected_raw or values[1]!=expected_zc or values[2]==0 or values[3]!=expected_zc*49*112 or values[4:]!=[0,0]:errors.append('oracle comparison did not pass')
    if not (out/'qemu-exit.txt').exists() or (out/'qemu-exit.txt').read_text().strip()!='0':errors.append('QEMU exit0 required')
    for name in ('guest-errors.log','qemu.stderr'):
        if not (out/name).exists() or (out/name).stat().st_size:errors.append(name+' not empty')
    library=out/'libf333-acquisition.a'
    result={'schema':'openmitrastar.f333-acquisition-oracle/v1','created_at':datetime.now(timezone.utc).isoformat(),
            'status':'PASS_PORTABLE_DECODER_VS_ORIGINAL_QEMU_LOOPS' if not errors else 'INCOMPLETE_OR_FAILED',
            'errors':errors,'suite':args.suite,'directory':str(out),'comparisons':values,'slices':slices,
            'library':{'path':str(library),'bytes':library.stat().st_size if library.exists() else 0,'sha256':sha(library) if library.exists() else None},
            'sources':{f.name:sha(f) for f in source.iterdir() if f.is_file()},'hardware_actions':False,'firmware_created':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'errors':errors,'path':str(out/'result.json'),'serial':serial,'stderr':p.stderr.decode(errors='replace')[-2000:]},indent=2))
    return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(main())
