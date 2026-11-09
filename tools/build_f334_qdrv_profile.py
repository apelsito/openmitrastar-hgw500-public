"""Reconstruct the F321 qdrv profile, then externalize only its radar provider."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib,json,shlex,shutil,subprocess
from pathlib import Path
import f334_qdrv_contract as elf

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=ROOT/'work/linux510-radio-port/quantenna'
SOURCE=ROOT/'work/linux510-radio-port/quantenna-f334-f321-profile'
BASELINE=ROOT/'outputs/preflight/f334-qdrv-profile-20260921T105210Z/qdrv-f321.ko'
PROVIDER=ROOT/'outputs/kernel-port/f325-radar-once-20260919T000320492832Z/qtn_radar_shadow_f315.ko'
PROVIDER_SHA='a59f3ae86b1ced8bf330f2748f42d4508017f1284bce77ad69151bf47b8bb13c'
KOUT='/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample'
KERNEL='/home/user/mitrastar-linux-5.10.260'
CONFIG_SHA='cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]

def prepare_source():
    if SOURCE.exists(): return
    for component in ('qdrv','wlan','mtest'):
        folder=ORIGINAL/component
        if not folder.exists():continue
        for src in folder.rglob('*'):
            if not src.is_file() or (src.suffix not in ('.c','.h','.S','.inc') and src.name!='Makefile') or src.name.endswith('.mod.c'):continue
            if component=='wlan' and src.name!='openmitrastar_beacon_preflight.h':continue
            dest=SOURCE/src.relative_to(ORIGINAL);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    target=SOURCE/'qdrv/qdrv_tx.c'
    if sha(target)!='f25c543b222ce19836787f4fd6745051bee3572838b508295c36939662e69de9':raise ValueError('canonical F168 TX source drift')
    text=target.read_text()
    old='static bool openmitrastar_txpool_probe_enable;\nmodule_param(openmitrastar_txpool_probe_enable, bool, 0400);\nMODULE_PARM_DESC(openmitrastar_txpool_probe_enable,\n\t"Sample HGW-500BNA HBM pools around AuC/TQE submission (diagnostic only)");\n'
    assert text.count(old)==1;text=text.replace(old,'')
    old='\tbool txpool_probe = hgw_target && READ_ONCE(openmitrastar_txpool_probe_enable);\n'
    assert text.count(old)==1;text=text.replace(old,'')
    assert text.count('if (txpool_probe)')==1;text=text.replace('if (txpool_probe)','if (hgw_target)')
    old='if (txpool_probe &&\n\t\t    (tqe_queued == NETDEV_TX_BUSY || (submit_total & 0x1ff) == 0))'
    assert text.count(old)==1;text=text.replace(old,'if (tqe_queued == NETDEV_TX_BUSY || (submit_total & 0x1ff) == 0)')
    target.write_text(text,encoding='ascii',newline='\n')
    (SOURCE/'Makefile').write_text('subdir-ccflags-y += -DOPENMITRASTAR_QDRV_V89_PAIR=1\nsubdir-ccflags-y += -DOPENMITRASTAR_SWITCH_EMAC_PORT=1 -DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1\nsubdir-ccflags-y += -ffile-prefix-map=$(src)='+linux(ORIGINAL)+'\nobj-m += qdrv/\n',encoding='ascii')

def main():
    assert sha(BASELINE)=='0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff'
    assert sha(PROVIDER)==PROVIDER_SHA
    prepare_source()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'outputs/kernel-port'/('f334-qdrv-profile-'+stamp);out.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(Path(__file__),out/Path(__file__).name)
    shutil.copytree(SOURCE,out/'source')
    q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
    sym=linux(ORIGINAL/'Module.symvers');radarsym=linux(ROOT/'outputs/kernel-port/f315-radar-shadow-20260905/provider-Module.symvers')
    script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
test "$(sha256sum {q(KOUT)}/.config | cut -d' ' -f1)" = {CONFIG_SHA}
cp {q(KOUT)}/.config "$out/kernel.config"
cp {q(KOUT)}/Module.symvers "$out/kernel-Module.symvers"
awk '$3 !~ /\\/qdrv\\/qdrv$/ {{print}}' {q(sym)} >"$out/dependencies.symvers"
for kind in baseline external-a external-b; do
 build=$(mktemp -d /home/user/openmitrastar-build/f334-qdrv-$kind-XXXXXXXX)
 echo "$build" >"$out/$kind-directory.txt"
 cp -a "$out/source"/. "$build"/
 if test "$kind" != baseline; then
  sed -i 's/qdrv_kernel_compat\\.o qdrv_radar_compat\\.o/qdrv_kernel_compat.o/' "$build/qdrv/Makefile"
 fi
 SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 \\
 make -C {q(KERNEL)} O={q(KOUT)} ARCH=arc CROSS_COMPILE="$tc" M="$build" QTN_GPL={q(linux(ROOT/'work/sources/Quantenna-GPL'))} KBUILD_EXTRA_SYMBOLS="$out/dependencies.symvers {q(radarsym)}" KBUILD_MODPOST_WARN=1 -j8 modules >"$out/$kind-build.log" 2>&1
 ! grep -Eq 'undefined!|ERROR: modpost|error:|frame size' "$out/$kind-build.log"
 cp "$build/qdrv/qdrv.ko" "$out/$kind.ko"
 cp "$build/Module.symvers" "$out/$kind-Module.symvers"
 modinfo "$out/$kind.ko" >"$out/$kind-modinfo.txt"
 "${{tc}}readelf" -x __param "$out/$kind.ko" >"$out/$kind-params.txt"
 "${{tc}}nm" -u "$out/$kind.ko" >"$out/$kind-imports.txt"
 find "$build/qdrv" -name '*.o.cmd' -type f -exec grep -h -m1 '^cmd_' {{}} + >"$out/$kind-compile-commands.txt"
done
cmp "$out/external-a.ko" "$out/external-b.ko"
'''
    (out/'build.sh').write_bytes(script.encode())
    p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','bash','--noprofile','--norc','-s'],input=script.encode(),capture_output=True,timeout=900)
    (out/'build.stdout.txt').write_bytes(p.stdout);(out/'build.stderr.txt').write_bytes(p.stderr)
    if p.returncode:
        print(json.dumps({'status':'BUILD_FAILED','output':str(out),'returncode':p.returncode}));return 1
    reference=elf.inspect(BASELINE);baseline=elf.inspect(out/'baseline.ko');candidate=elf.inspect(out/'external-a.ko')
    elf.assert_profile(baseline,reference);elf.assert_profile(candidate,reference)
    text_equal=reference['section_hashes']['.text']==baseline['section_hashes']['.text']
    comparison={'reference':reference,'baseline':baseline,'candidate':candidate,'baseline_text_equal':text_equal,'external_reproducible':sha(out/'external-a.ko')==sha(out/'external-b.ko')}
    (out/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n',encoding='ascii')
    if not text_equal:
        print(json.dumps({'status':'BASELINE_TEXT_DIFF_REQUIRES_REVIEW','output':str(out),'reference_size':reference['bytes'],'baseline_size':baseline['bytes']}));return 2
    shutil.copyfile(out/'external-a.ko',out/'qdrv-f334-external-radar.ko')
    shutil.copyfile(PROVIDER,out/'qtn_radar_shadow_f315.ko')
    sources=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sorted(SOURCE.rglob('*')) if p.is_file()]
    result={'schema':'openmitrastar.f334-qdrv-profile/v1','status':'PASS_OFFLINE_DIAGNOSTIC_MODULE','created_at_utc':datetime.now(timezone.utc).isoformat(),
      'baseline_text_equal':True,'baseline_qdrv_sha256':reference['sha256'],'kernel_config_sha256':CONFIG_SHA,
      'provider':{'file':'qtn_radar_shadow_f315.ko','sha256':PROVIDER_SHA,'changed':False},
      'qdrv':{'file':'qdrv-f334-external-radar.ko','sha256':candidate['sha256'],'bytes':candidate['bytes'],'reproducible':True},
      'authority':{'radar_start':False,'radar_get_status':False,'callbacks':0,'dfs_tx':False},
      'sources':sources,'hardware_actions':False,'firmware_created':False,'physical_acceptance':False}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps({'status':result['status'],'output':str(out),'qdrv':result['qdrv']},indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
