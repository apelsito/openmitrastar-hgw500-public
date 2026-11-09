"""F339 internal Topaz hwmon: isolated Linux 5.10 build and OEM software oracle.

No hardware, network, firmware image, flash or edits to existing kernel trees.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,struct,subprocess
from dtb_find_nodes import parse

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'work/kernel-port/versions/f339-topaz-hwmon'
OEM=ROOT/'work/sources/Quantenna-GPL/drivers/topaz/temp_sens.c'
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
F321=DEVICE/'firmware/f321-f314-device-bound'
BASE='openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(test,message):
    if not test:raise ValueError(message)
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def nodes(path):return {n['path']:dict(n['props']) for n in parse(path)}
def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/kernel-port'/('f339-topaz-hwmon-'+stamp);out.mkdir(exist_ok=False)
    require(sha(OEM)=='ef542efef64406330610e6b504082dea4e2692e4f87041fe3d35cac3879bee41','OEM source changed')
    require(sha(F321/(BASE+'.config'))=='cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e','F321 config changed')
    require(sha(F321/(BASE+'.dtb'))=='7063f6b1f7b0180226c0d0fc6fd0ecd2659e18463664d42dd2a88726a2e80d81','F321 DT changed')
    original=OEM.read_text();fragment=original[original.index('#define TOPAZ_TEMPSENS_INIT_VAL'):original.index('EXPORT_SYMBOL(topaz_read_internal_temp_sens)')]
    old_table=[int(n) for n in re.search(r'code_idx\[[^\]]+\]\s*=\s*\{([^}]+)',fragment,re.S)[1].replace('\n','').split(',')]
    new_table=[int(n) for n in re.search(r'f339_code_idx\[34\]\s*=\s*\{([^}]+)',(SRC/'topaz_temp_core.h').read_text(),re.S)[1].replace('\n','').split(',')]
    require(old_table==new_table and len(old_table)==34,'OEM table mismatch')
    writes=re.findall(r'\bwritel\([^;]+;',original);require(len(writes)==3,'OEM init protocol changed')
    oracle='''#define TOPAZ_SYS_CTL_TEMP_SENS_DATA 8u
#define TOPAZ_SYS_CTL_TEMP_SENS_DATA_TEMP 0xfffu
#define TOPAZ_SYS_CTL_TEMPSENS_CTL 0u
#define TOPAZ_SYS_CTL_TEMPSENS_CTL_SHUTDWN 2u
#define TOPAZ_SYS_CTL_TEMPSENS_CTL_START_CONV 1u
static unsigned int oracle_word,oracle_writes,oracle_values[4];
static unsigned int readl(unsigned int a){(void)a;return oracle_word;}
static void writel(unsigned int v,unsigned int a){(void)a;oracle_values[oracle_writes++]=v;}
'''+fragment+'\nstatic void oem_write_sequence(void){\n'+'\n'.join(writes)+'\n}\n'
    (out/'oem_oracle.inc').write_text(oracle,newline='\n')
    source_pins={str(p):sha(p) for p in SRC.iterdir() if p.is_file()}
    source_pins[str(OEM)]=sha(OEM)
    (out/'base-f321.config').write_bytes((F321/(BASE+'.config')).read_bytes())
    (out/'base-f321.dtb').write_bytes((F321/(BASE+'.dtb')).read_bytes())
    q=shlex.quote;build='/home/user/openmitrastar-build/f339-topaz-hwmon-'+stamp
    tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
    script=f'''set -eu
out={q(linux(out))}
overlay={q(linux(SRC))}
build={q(build)}
tc={q(tc)}
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -I"$out" -I"$overlay" "$overlay/test_temp_core.c" -o "$out/test-temp-core"
"$out/test-temp-core" > "$out/oracle-tests.log"
test ! -e "$build"
mkdir "$build"
cp -a --reflink=auto /home/user/mitrastar-linux-5.10.260 "$build/linux"
src="$build/linux"
dtc -I dtb -O dts "$out/base-f321.dtb" > "$out/f339-default.dts" 2> "$out/dtc-base.log"
cat "$overlay/topaz-internal-temperature.dtsi" >> "$out/f339-default.dts"
dtc -I dts -O dtb "$out/f339-default.dts" -o "$out/f339-default.dtb" 2> "$out/dtc-default.log"
cp "$out/f339-default.dts" "$out/f339-ownership-example.dts"
cat >> "$out/f339-ownership-example.dts" <<'F339_EOF'
&{{/soc/recovery@e0000000}} {{ reg = <0xe0000000 0x8 0xf1000000 0x40 0xf4000000 0x20>; }};
F339_EOF
dtc -I dts -O dtb "$out/f339-ownership-example.dts" -o "$out/f339-ownership-example.dtb" 2> "$out/dtc-ownership.log"
cp "$out/f339-default.dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
for lane in a b; do
 kout="$build/$lane"
 mod="$build/module-$lane"
 mkdir "$kout" "$mod" "$out/$lane"
 cp "$out/base-f321.config" "$kout/.config"
 "$src/scripts/config" --file "$kout/.config" --module HWMON
 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" olddefconfig > "$out/config-$lane.log" 2>&1
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_VERSION=339 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f339-hwmon make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" KCFLAGS="-ffile-prefix-map=$kout=/f339-kernel" -j4 vmlinux modules dtbs > "$out/build-$lane.log" 2>&1
 cp "$overlay/temp_sens.c" "$overlay/topaz_temp_core.h" "$overlay/Makefile" "$mod/"
 SOURCE_DATE_EPOCH=1790006400 make -s -C "$src" O="$kout" M="$mod" ARCH=arc CROSS_COMPILE="$tc" KCFLAGS="-ffile-prefix-map=$mod=/f339-module" -j4 modules > "$out/module-$lane.log" 2>&1
 cp "$kout/vmlinux" "$out/$lane/f339.vmlinux"
 cp "$kout/.config" "$out/$lane/f339.config"
 cp "$kout/Module.symvers" "$out/$lane/Module.symvers"
 cp "$kout/drivers/hwmon/hwmon.ko" "$out/$lane/"
 cp "$mod/temp_sens.ko" "$out/$lane/"
 for name in hwmon temp_sens; do
  "${{tc}}strip" --strip-debug "$out/$lane/$name.ko"
  "${{tc}}readelf" -h "$out/$lane/$name.ko" > "$out/$lane/$name.elf.txt"
  "${{tc}}nm" "$out/$lane/$name.ko" > "$out/$lane/$name.symbols.txt"
 done
done
cmp "$out/a/temp_sens.ko" "$out/b/temp_sens.ko"
cmp "$out/a/hwmon.ko" "$out/b/hwmon.ko"
cmp "$out/a/f339.vmlinux" "$out/b/f339.vmlinux"
'''
    (out/'build.sh').write_text(script,newline='\n');print(json.dumps({'started':str(out),'hardware_actions':False}),flush=True)
    run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
    # Exact configured distro; never discover or start unrelated runtime targets.
    (out/'launcher.stdout').write_bytes(run.stdout);(out/'launcher.stderr').write_bytes(run.stderr)
    result=dict(schema='openmitrastar.f339-topaz-hwmon-build/v1',status='BUILD_FAILED',returncode=run.returncode,hardware_actions=False,firmware_created=False,source_pins=source_pins,isolated_build=build)
    if run.returncode==0:
        base=nodes(out/'base-f321.dtb');default=nodes(out/'f339-default.dtb');example=nodes(out/'f339-ownership-example.dtb')
        require(all(default[k]==v for k,v in base.items()),'default DT changed original nodes')
        sensor='/soc/temperature-sensor@e0000108';require(default[sensor]['status']==b'disabled\0','sensor automatically enabled')
        require(default[sensor]==example[sensor],'ownership example changed sensor enablement')
        require(struct.unpack('>6I',example['/soc/recovery@e0000000']['reg'])==(0xe0000000,8,0xf1000000,0x40,0xf4000000,0x20),'ownership split changed unrelated maps')
        text=(out/'oracle-tests.log').read_text();require(re.fullmatch(r'PASS F339 code_vectors=4096 readiness_vectors=4096 checks=\d+ hardware_actions=0\n',text),'oracle did not pass')
        require('CONFIG_HWMON=m' in (out/'a/f339.config').read_text().splitlines(),'HWMON missing')
        result.update(status='PASS_OFFLINE_HWMON_OEM_ORACLE',reproducible=True,oracle=text.strip(),dt_default_disabled=True,clock_and_hardware_acceptance=False,
                      artifacts={name:{'bytes':(out/'a'/name).stat().st_size,'sha256':sha(out/'a'/name)} for name in ['temp_sens.ko','hwmon.ko','f339.vmlinux','f339.config']})
    require(all(sha(p)==h for p,h in source_pins.items()),'source changed during build')
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),'status':result['status']},indent=2));return 0 if run.returncode==0 else 1
if __name__=='__main__':raise SystemExit(main())
