"""Relink exact corrected F334 qdrv profile against the F332 provider ABI."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shlex,shutil,subprocess
import f334_qdrv_contract as contract
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/linux510-radio-port/quantenna-f334-f321-profile'
REFERENCE=ROOT/'outputs/kernel-port/f334-qdrv-profile-20260921T105936Z'
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--provider-symvers',type=Path,required=True);args=ap.parse_args();symvers=args.provider_symvers.resolve()
 reference=json.loads((REFERENCE/'manifest.json').read_text());require(reference['status']=='PASS_OFFLINE_DIAGNOSTIC_MODULE','F334 profile qualification missing')
 require(sha(REFERENCE/'qdrv-f334-external-radar.ko')==reference['qdrv']['sha256'],'F334 qdrv hash drift')
 for row in reference['sources']:require(sha(ROOT/row['path'])==row['sha256'],'F334 source drift '+row['path'])
 rows=[line.split() for line in symvers.read_text().splitlines() if line.strip()]
 require(len(rows)==18 and all(Path(r[2]).name=='qtn_radar_f332' for r in rows),'unexpected F332 provider API')
 out=BASE/('f332-qdrv-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 shutil.copytree(SOURCE,out/'source');(out/'provider.symvers').write_bytes(symvers.read_bytes())
 dependencies=[]
 for line in (ROOT/'work/linux510-radio-port/quantenna/Module.symvers').read_text().splitlines():
  if line.split()[2].replace('\\','/').endswith('/qdrv/qdrv'):continue
  dependencies.append(line)
 (out/'dependencies.symvers').write_bytes(('\n'.join(dependencies)+'\n').encode())
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-');q=shlex.quote
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src=/home/user/mitrastar-linux-5.10.260
kout=/home/user/openmitrastar-build/f300-emac-hw-demand-two-sample
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e
for lane in a b; do
 build=$(mktemp -d /home/user/openmitrastar-build/f332-qdrv-$lane-XXXXXXXX)
 printf '%s\\n' "$build" > "$out/build-$lane-directory.txt"
 cp -a "$out/source"/. "$build"/
 sed -i 's/qdrv_kernel_compat\\.o qdrv_radar_compat\\.o/qdrv_kernel_compat.o/' "$build/qdrv/Makefile"
 SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build" QTN_GPL={q(linux(ROOT/'work/sources/Quantenna-GPL'))} KBUILD_EXTRA_SYMBOLS="$out/dependencies.symvers $out/provider.symvers" -j8 modules > "$out/build-$lane.log" 2>&1
 cp "$build/qdrv/qdrv.ko" "$out/qdrv-$lane.ko"
 cp "$build/Module.symvers" "$out/Module-$lane.symvers"
 find "$build/qdrv" -name '*.o.cmd' -type f -exec grep -h -m1 '^cmd_' {{}} + > "$out/compile-$lane.txt"
done
cmp "$out/qdrv-a.ko" "$out/qdrv-b.ko"
'''
 (out/'build.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','bash',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True,timeout=900)
 (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
 errors=[];details=None
 if p.returncode:errors.append('qdrv build failed')
 else:
  expected=contract.inspect(REFERENCE/'qdrv-f334-external-radar.ko');actual=contract.inspect(out/'qdrv-a.ko');contract.assert_profile(actual,expected)
  if contract.normalized_functions(REFERENCE/'qdrv-f334-external-radar.ko')!=contract.normalized_functions(out/'qdrv-a.ko'):errors.append('qdrv code differs from F334 beyond link metadata')
  deps=next(x for x in actual['modinfo'] if x.startswith('depends='))
  if 'qtn_radar_f332' not in deps or 'qtn_radar_shadow_f315' in deps:errors.append('wrong radar module dependency')
  for lane in ('a','b'):
   lines=[s for s in (out/('compile-'+lane+'.txt')).read_text().splitlines() if ' -c ' in s and '.mod.c' not in s]
   if len(lines)<30 or not all(all(flag in s for flag in ('-DOPENMITRASTAR_QDRV_V89_PAIR=1','-DOPENMITRASTAR_SWITCH_EMAC_PORT=1','-DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1')) for s in lines):errors.append('F321 profile flags missing')
  details={'path':str(out/'qdrv-a.ko'),'sha256':sha(out/'qdrv-a.ko'),'bytes':(out/'qdrv-a.ko').stat().st_size,'dependencies':deps,'parameters':actual['parameters']}
 report={'schema':'openmitrastar.f332-qdrv-link/v1','status':'PASS_F334_PROFILE_F332_ABI' if not errors else 'FAIL','errors':errors,'qdrv':details,'provider_symvers_sha256':sha(symvers),'provider_exports':[r[1] for r in rows],'F334_reference_sha256':reference['qdrv']['sha256'],'code_normalized_equal':not errors,'reproducible':not errors,'hardware_actions':False,'firmware_created':False}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**report},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
