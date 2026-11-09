"""Compile two private F328 kernel engines; never load a module or touch HGW."""
import argparse,hashlib,json,shlex,subprocess
from pathlib import Path
from datetime import datetime,timezone
from elftools.elf.elffile import ELFFile
from f328_oem_classifier_projection import require,EXPECTED
from build_f328_oem_classifier_offline import linux,validate_run
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f328_oem_classifier'
PRIVATE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--oracle-dir',required=True,type=Path)
    args=parser.parse_args();oracle=args.oracle_dir.resolve()
    report=json.loads((oracle/'result.json').read_text());proof=json.loads((oracle/'projection.json').read_text())
    require(report['status']=='PASS_EXACT_CLASSIFIER_SYNTHETIC_QEMU','oracle qualification missing')
    require(validate_run(oracle)['passed'],'oracle evidence no longer accepted')
    require(proof['oem_sha256']==EXPECTED and sha(oracle/'f328-oem-classifier.o')==proof['projection_sha256'],'projection provenance mismatch')
    require(json.loads((oracle/'eu-profile-audit.json').read_text())['legacy_hz']==200,'legacy clock unattested')
    require(sha(oracle/'eu-profile.h')==report['artifacts']['eu-profile.h']['sha256'],'profile header drift')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=PRIVATE/('f328-kernel-engine-'+stamp);out.mkdir(parents=True,exist_ok=False)
    files=('Makefile','f328_kernel_engine.c','f328_kernel_engine.h','f328_legacy_abi.c','f328_legacy_abi.h')
    for lane in ('a','b'):
        path=out/lane;path.mkdir()
        for name in files:(path/name).write_bytes((SOURCE/name).read_bytes())
        for name in ('f328-oem-classifier.o','eu-profile.h'):(path/name).write_bytes((oracle/name).read_bytes())
    tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    q=shlex.quote
    script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src=/home/user/mitrastar-linux-5.10.260
kout=/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
test "$(make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" kernelrelease)" = 5.10.260-openmitrastar-radiohw
for lane in a b; do
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 \\
 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane" KCFLAGS="-ffile-prefix-map=$out/$lane=/f328-source" -j2 modules > "$out/build-$lane.log" 2>&1
 "${{tc}}nm" -u "$out/$lane/f328_oem_engine.ko" > "$out/imports-$lane.txt"
 "${{tc}}readelf" -h "$out/$lane/f328_oem_engine.ko" > "$out/header-$lane.txt"
done
cmp "$out/a/f328_oem_engine.ko" "$out/b/f328_oem_engine.ko"
'''
    (out/'build.sh').write_bytes(script.encode())
    p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
    (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
    require(p.returncode==0,'kernel qualification failed; preserve '+str(out))
    module=out/'a/f328_oem_engine.ko'
    imports={line.split()[-1] for line in (out/'imports-a.txt').read_text().splitlines() if line.strip()}
    require(imports=={'memcpy','memset','mutex_lock','mutex_unlock'},'unexpected kernel imports '+str(imports))
    vmlinux=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.vmlinux'
    with vmlinux.open('rb') as stream:
        exports=ELFFile(stream).get_section_by_name('.symtab')
        require(all(exports.get_symbol_by_name('__ksymtab_'+name) for name in imports),'missing exact F321 kernel export')
    with module.open('rb') as stream:
        elf=ELFFile(stream);info=elf.get_section_by_name('.modinfo').data()
        require(b'license=Proprietary\0' in info,'OEM license must not be changed to bypass exports')
        require(b'vermagic=5.10.260-openmitrastar-radiohw' in info,'wrong target kernel')
        symbols=elf.get_section_by_name('.symtab')
        require(all(symbols.get_symbol_by_name(name) for name in ('f328_engine_begin','f328_engine_batch','f328_engine_end')),'engine API incomplete')
        require(not symbols.get_symbol_by_name('radar_start') and not symbols.get_symbol_by_name('radar_poll_work'),'old hardware lifecycle included')
    manifest={'schema':'openmitrastar.f328-kernel-engine-offline/v1','created_at':datetime.now(timezone.utc).isoformat(),
              'status':'PASS_OFFLINE_KERNEL_COMPILE_NO_LOAD','module':{'path':str(module),'bytes':module.stat().st_size,'sha256':sha(module)},
              'oracle_result':str(oracle/'result.json'),'oracle_result_sha256':sha(oracle/'result.json'),
              'kernel':'5.10.260-openmitrastar-radiohw','legacy_hz':200,'linux510_hz':100,
              'kernel_config_sha256':'cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e',
              'kernel_export_proof_vmlinux':str(vmlinux),'kernel_export_proof_vmlinux_sha256':sha(vmlinux),
              'clock_input':'monotonic nanoseconds divided by5000000 with OEM32bit wrap',
              'reproducible':sha(module)==sha(out/'b/f328_oem_engine.ko'),'license':'Proprietary',
              'kernel_imports':sorted(imports),'module_loaded':False,'firmware_created':False,
              'hardware_actions':False,'postfilter':False,'callback_authority':False,
              'sources':{n:sha(SOURCE/n) for n in files}}
    (out/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
