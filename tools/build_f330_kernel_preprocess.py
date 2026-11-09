"""Reproducible private Linux 5.10 module for F330; no loading or hardware."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shlex,subprocess
from elftools.elf.elffile import ELFFile
from f328_oem_classifier_projection import require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/modules/f330_oem_preprocess'
PRIVATE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):p=p.resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--oracle-dir',type=Path,required=True);args=parser.parse_args()
    base=args.oracle_dir.resolve();proof=json.loads((base/'result.json').read_text())
    require(proof['status']=='PASS_ORIGINAL_PREPROCESS_QEMU_NO_HARDWARE','unaccepted oracle')
    require((base/'qemu-exit.txt').read_text().strip()=='0','oracle exit mismatch')
    require(sha(base/'f330-oem-preprocess.o')==proof['projection']['object_sha256'],'projection mismatch')
    require(sha(base/'eu-profile.h')==proof['files']['eu-profile.h']['sha256'],'profile drift')
    require(sha(SOURCE/'f330_preprocess.c')==sha(base/'source/f330_preprocess.c'),'shared core changed since oracle')
    out=PRIVATE/('f330-kernel-preprocess-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
    names=('Makefile','f330_preprocess.c','f330_preprocess.h','f330_kernel_module.c')
    for lane in ('a','b'):
        target=out/lane;target.mkdir()
        for name in names:(target/name).write_bytes((SOURCE/name).read_bytes())
        for name in ('f330-oem-preprocess.o','eu-profile.h'):(target/name).write_bytes((base/name).read_bytes())
    tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');q=shlex.quote
    script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src=/home/user/mitrastar-linux-5.10.260
kout=/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
for lane in a b; do
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane" KCFLAGS="-ffile-prefix-map=$out/$lane=/f330-source" -j2 modules > "$out/build-$lane.log" 2>&1
 "${{tc}}nm" -u "$out/$lane/f330_preprocess_engine.ko" > "$out/imports-$lane.txt"
done
cmp "$out/a/f330_preprocess_engine.ko" "$out/b/f330_preprocess_engine.ko"
'''
    (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=180)
    (out/'build.stdout').write_bytes(p.stdout);(out/'build.stderr').write_bytes(p.stderr);require(p.returncode==0,'kernel build failed: '+str(out))
    module=out/'a/f330_preprocess_engine.ko'
    imports={s.split()[-1] for s in (out/'imports-a.txt').read_text().splitlines() if s.strip()}
    require(imports<={'mutex_lock','mutex_unlock','memcpy','memset'},'unexpected kernel dependency')
    with module.open('rb') as stream:
        elf=ELFFile(stream);info=elf.get_section_by_name('.modinfo').data()
        require(b'license=Proprietary\0' in info and b'vermagic=5.10.260-openmitrastar-radiohw' in info,'module contract drift')
        require(hashlib.sha256(elf.get_section_by_name('.text.f330_oem').data()).hexdigest()==proof['projection']['projected_text_sha256'],'preprocessor code changed')
    report={'schema':'openmitrastar.f330-kernel-preprocess/v1','status':'PASS_OFFLINE_REPRODUCIBLE_KERNEL_NO_LOAD',
            'created_at':datetime.now(timezone.utc).isoformat(),'module':{'path':str(module),'bytes':module.stat().st_size,'sha256':sha(module)},
            'reproducible':sha(module)==sha(out/'b/f330_preprocess_engine.ko'),'imports':sorted(imports),
            'oracle_path':str(base/'result.json'),'oracle_sha256':sha(base/'result.json'),
            'sources':{n:sha(SOURCE/n) for n in names},'module_loaded':False,'actual_hardware':False,'firmware':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
