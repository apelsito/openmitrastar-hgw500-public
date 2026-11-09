"""Build F339 replacement twice against its completed, hash-preserved kernel.

The earlier full build completed Linux and hwmon; only external-driver -Wextra
failed on old kernel headers. Reuse is explicit, never claimed as two kernel builds.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,shlex,subprocess
import build_f339_topaz_hwmon as b

def main():
    previous=b.ROOT/'outputs/kernel-port/f339-topaz-hwmon-20260921T132841Z';old=json.loads((previous/'result.json').read_text())
    b.require(old['status']=='BUILD_FAILED' and old['isolated_build']=='/home/user/openmitrastar-build/f339-topaz-hwmon-20260921T132841Z','unexpected kernel seed')
    b.require(b.sha(b.OEM)==old['source_pins'][str(b.OEM)],'OEM source changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=b.ROOT/'outputs/kernel-port'/('f339-hwmon-qualified-'+stamp);out.mkdir(exist_ok=False)
    inputs={str(p):b.sha(p) for p in b.SRC.iterdir() if p.is_file()};inputs[str(Path(__file__).resolve())]=b.sha(__file__)
    qdrv=b.ROOT/'work/linux510-radio-port/quantenna-f334-f321-profile/qdrv/qdrv_wlan.c';inputs[str(qdrv)]=b.sha(qdrv)
    for name in ['oem_oracle.inc','base-f321.config','base-f321.dtb','f339-default.dtb','f339-ownership-example.dtb']:(out/name).write_bytes((previous/name).read_bytes())
    q=shlex.quote;build='/home/user/openmitrastar-build/f339-hwmon-qualified-'+stamp
    script=f'''set -eu
out={q(b.linux(out))}
overlay={q(b.linux(b.SRC))}
build={q(build)}
src={q(old['isolated_build']+'/linux')}
kout={q(old['isolated_build']+'/a')}
tc={q(b.linux(b.ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-'))}
test ! -e "$build"
mkdir "$build" "$out/kernel-input"
sha256sum "$kout/vmlinux" "$kout/.config" "$kout/Module.symvers" "$kout/drivers/hwmon/hwmon.ko" "$src/drivers/hwmon/hwmon.c" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts" > "$out/kernel-inputs.sha256"
cp "$kout/vmlinux" "$out/kernel-input/f339.vmlinux"
cp "$kout/.config" "$out/kernel-input/f339.config"
cp "$kout/Module.symvers" "$out/kernel-input/Module.symvers"
cp "$kout/drivers/hwmon/hwmon.ko" "$out/kernel-input/hwmon.ko"
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -I"$out" -I"$overlay" "$overlay/test_temp_core.c" -o "$out/test-temp-core"
"$out/test-temp-core" > "$out/oracle-tests.log"
mkdir -p "$out/qdrv-check/qdrv"
cp {q(b.linux(qdrv))} "$out/qdrv-check/qdrv/qdrv_wlan.c"
patch --dry-run -p1 -d "$out/qdrv-check" < "$overlay/qdrv-consumer-error.patch" > "$out/qdrv-patch-check.log"
for lane in a b; do
 mod="$build/module-$lane"
 mkdir "$mod" "$out/$lane"
 cp "$overlay/temp_sens.c" "$overlay/topaz_temp_core.h" "$overlay/Makefile" "$mod/"
 SOURCE_DATE_EPOCH=1790006400 make -s -C "$src" O="$kout" M="$mod" ARCH=arc CROSS_COMPILE="$tc" KCFLAGS="-ffile-prefix-map=$mod=/f339-module" -j4 modules > "$out/module-$lane.log" 2>&1
 cp "$mod/temp_sens.ko" "$out/$lane/temp_sens.ko"
 "${{tc}}strip" --strip-debug "$out/$lane/temp_sens.ko"
 "${{tc}}readelf" -h "$out/$lane/temp_sens.ko" > "$out/$lane/elf.txt"
 "${{tc}}nm" "$out/$lane/temp_sens.ko" > "$out/$lane/symbols.txt"
done
cmp "$out/a/temp_sens.ko" "$out/b/temp_sens.ko"
sha256sum -c "$out/kernel-inputs.sha256" > "$out/kernel-inputs-unchanged.log"
'''
    (out/'build.sh').write_text(script,newline='\n');print(json.dumps({'started':str(out),'hardware_actions':False}),flush=True)
    run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',b.linux(out/'build.sh')],capture_output=True)
    (out/'launcher.stdout').write_bytes(run.stdout);(out/'launcher.stderr').write_bytes(run.stderr)
    report=dict(schema='openmitrastar.f339-qualified-hwmon/v1',status='BUILD_FAILED',returncode=run.returncode,hardware_actions=False,firmware_created=False,source_pins=inputs,kernel_seed_result=str(previous/'result.json'),kernel_seed_result_sha256=b.sha(previous/'result.json'),kernel_rebuilt=False,independent_kernel_reproducibility_claimed=False)
    if not run.returncode:
        from elftools.elf.elffile import ELFFile
        with (out/'a/temp_sens.ko').open('rb') as f:
            elf=ELFFile(f);b.require(elf.header['e_machine']=='EM_ARC_COMPACT','wrong driver ABI');sym=elf.get_section_by_name('.symtab')
            imports={s.name for s in sym.iter_symbols() if s['st_shndx']=='SHN_UNDEF' and s.name};export_names={line.split()[1] for line in (out/'kernel-input/Module.symvers').read_text().splitlines()}
            b.require(imports<=export_names,'unresolved driver imports: '+str(sorted(imports-export_names)))
        b.require((out/'a/temp_sens.ko').read_bytes()==(out/'b/temp_sens.ko').read_bytes(),'driver not reproducible')
        b.require('CONFIG_HWMON=m' in (out/'kernel-input/f339.config').read_text().splitlines(),'wrong kernel configuration')
        b.require(b.nodes(out/'f339-default.dtb')['/soc/temperature-sensor@e0000108']['status']==b'disabled\0','auto-enabled sensor')
        oracle=(out/'oracle-tests.log').read_text().strip();b.require(oracle.startswith('PASS F339 ') and 'checks=17584 ' in oracle,'oracle failed')
        report.update(status='PASS_OFFLINE_HWMON_OEM_ORACLE',driver_reproducible=True,kernel_inputs_unchanged=True,oracle=oracle,unresolved_imports=[],dt_default_disabled=True,
            artifacts={name:{'path':str(out/rel),'bytes':(out/rel).stat().st_size,'sha256':b.sha(out/rel)} for name,rel in [('temp_sens.ko','a/temp_sens.ko'),('hwmon.ko','kernel-input/hwmon.ko'),('kernel','kernel-input/f339.vmlinux'),('config','kernel-input/f339.config'),('dt_default','f339-default.dtb'),('dt_ownership','f339-ownership-example.dtb')]})
    b.require(all(b.sha(p)==h for p,h in inputs.items()),'inputs changed during build')
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'result':str(out/'result.json')},indent=2));return run.returncode
if __name__=='__main__':raise SystemExit(main())
