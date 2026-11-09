"""Compile only the two observed modules and resolve their real module closure."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,shutil,subprocess
from build_f367r7_clock_component import inspect
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=ROOT/'work/kernel-port/f367r9-transition-observation'
OVERLAY=ROOT/'versions/lyoko-foundation-6.11.8-f367r9-transition-observation/overlay'
BASE=DEVICE/'firmware/f367r8-f365-mode-contract-device-bound'
KERNEL=Path('/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/result.json')
REUSE=Path('/workspace/OpenMitraStar-build/f367r7/f367r7-clock-20260922T193754Z/result.json')
TEST=ROOT/'outputs/preflight/f367r9-transition-observation-20260922T222752Z/result.json'
HOST_TEST=ROOT/'outputs/preflight/f367r9-hostlink-trace-20260922T221600Z/result.json'
PEER_CMD=ROOT/'work/linux510-radio-port/quantenna/wlan/.ieee80211_wireless.o.cmd'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):p=Path(p);return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=sha(p))
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def require(value,why):
 if not value:raise ValueError(why)
def main():
 source=json.loads((SOURCE/'source-manifest.json').read_text());base=json.loads((BASE/'manifest.json').read_text());kernel=json.loads(KERNEL.read_text());reuse=json.loads(REUSE.read_text())
 test=json.loads(TEST.read_text());host_test=json.loads(HOST_TEST.read_text())
 require(test['status']=='PASS_TRANSITION_OBSERVATION_PRESERVES_SEMANTICS' and all(test['checks'].values()),'boundary test not passed')
 require(host_test['status']=='PASS_OBSERVATION_PATCH_PRESERVES_ORIGINAL' and all(host_test['checks'].values()),'hostlink test not passed')
 for proof in (test,host_test):
  for path,digest in proof['source_pins'].items():require(sha(path)==digest,'test source drift '+path)
 for name,digest in source['source_pins'].items():require(sha(SOURCE/name)==digest,'R9 source drift '+name)
 for path,digest in source['overlay_pins'].items():require(sha(path)==digest,'overlay drift')
 rootfs=BASE/base['artifacts']['rootfs_squashfs']['file'];require(sha(rootfs)==base['artifacts']['rootfs_squashfs']['sha256'],'R8 rootfs drift')
 require(reuse['status']=='PASS_F367R7_CLOCK_COMPONENTS','prior native components unqualified')
 parent_flags=sorted(set(re.findall(r'-DOPENMITRASTAR_[A-Za-z0-9_=]+',PEER_CMD.read_text().splitlines()[0])))
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=Path('/workspace/OpenMitraStar-build/f367r9')/('f367r9-transition-'+stamp);out.mkdir(parents=True,exist_ok=False)
 shutil.copytree(SOURCE,out/'source')
 olddeps=Path(kernel['completed_build'])/'a/dependencies.symvers'
 olddeps=olddeps.read_text().splitlines();wlan_exports=set(reuse['modules']['wlan']['exports'])
 # Remove the old wlan's own exports while compiling its replacement.
 (out/'peer-build.symvers').write_bytes(('\n'.join(row for row in olddeps if row.split()[1] not in wlan_exports)+'\n').encode())
 provider=Path(reuse['artifacts']['provider']['path']);provider_sym=provider.parent/'provider.symvers'
 shutil.copyfile(kernel['artifacts']['Module.symvers']['path'],out/'kernel.symvers')
 compat=Path(source['peer_compat_root']);q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
 build='/home/user/openmitrastar-build/f367r9-transition-'+stamp
 script=f'''set -eu
out={q(linux(out))}
build={q(build)}
src={q(kernel['kernel_source_linux'])}
tc={q(tc)}
test ! -e "$build"
mkdir "$build"
cp -a --reflink=auto {q(kernel['kernel_build_directory_linux'])} "$build/kernel-context"
kout="$build/kernel-context"
unsquashfs -processors 1 -no-progress -d "$out/baseline-rootfs" {q(linux(rootfs))} > "$out/extract.log"
for lane in a b; do
 cp -a "$out/source" "$build/$lane"
 SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build/$lane/wlan" QTN_GPL={q(linux(ROOT/'work/sources/Quantenna-GPL'))} QDRV_COMPAT={q(linux(compat))} KBUILD_EXTRA_SYMBOLS="$out/peer-build.symvers" KCFLAGS="{' '.join(parent_flags)} -I{linux(ROOT/'work/linux510-radio-port/quantenna/wlan')} -ffile-prefix-map=$build/$lane/wlan=/f367r9-wlan" -j4 modules > "$out/wlan-$lane.log" 2>&1
 cat "$out/peer-build.symvers" "$build/$lane/wlan/Module.symvers" {q(linux(provider_sym))} > "$build/$lane/dependencies.symvers"
 SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build/$lane/qdrv" QTN_GPL={q(linux(ROOT/'work/sources/Quantenna-GPL'))} KBUILD_EXTRA_SYMBOLS="$build/$lane/dependencies.symvers" KCFLAGS="-ffile-prefix-map=$build/$lane=/f366-source" -j4 modules > "$out/qdrv-$lane.log" 2>&1
 mkdir "$out/$lane"
 cp "$build/$lane/wlan/wlan.ko" "$out/$lane/wlan.ko"
 cp "$build/$lane/qdrv/qdrv/qdrv.ko" "$out/$lane/qdrv.ko"
 cp "$build/$lane/wlan/Module.symvers" "$out/$lane/wlan.symvers"
 cp "$build/$lane/qdrv/Module.symvers" "$out/$lane/qdrv.symvers"
done
cmp "$out/a/wlan.ko" "$out/b/wlan.ko"
cmp "$out/a/qdrv.ko" "$out/b/qdrv.ko"
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps(dict(build_started=str(out),hardware_actions=False)),flush=True)
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr);require(run.returncode==0,'R9 build failed '+str(out))
 modules={};owners={};types={};kernel_exports={}
 for row in (out/'kernel.symvers').read_text().splitlines():v=row.split();kernel_exports[v[1]]=v[3]
 for p in sorted((out/'baseline-rootfs/lib/modules').rglob('*.ko')):
  info,imports,exports,et=inspect(p)
  if info['name'] in ('qdrv','wlan'):continue
  modules[info['name']]={**item(p),'info':info,'imports':sorted(imports),'exports':sorted(exports),'edges':set()}
  for symbol in exports:require(symbol not in owners,'duplicate export '+symbol);owners[symbol]=info['name'];types[symbol]=et[symbol]
 for p in (out/'a/wlan.ko',out/'a/qdrv.ko'):
  info,imports,exports,et=inspect(p);modules[info['name']]={**item(p),'info':info,'imports':sorted(imports),'exports':sorted(exports),'edges':set()}
  for symbol in exports:require(symbol not in owners and symbol not in kernel_exports,'duplicate new export '+symbol);owners[symbol]=info['name'];types[symbol]=et[symbol]
 for p in (out/'peer-build.symvers',out/'a/wlan.symvers',out/'a/qdrv.symvers',provider_sym):
  for row in p.read_text().splitlines():v=row.split();types[v[1]]=v[3]
 audited=[]
 for name,row in modules.items():
  for symbol in row['imports']:
   owner='vmlinux' if symbol in kernel_exports else owners.get(symbol);require(owner is not None,'unresolved '+name+':'+symbol)
   typ=kernel_exports[symbol] if owner=='vmlinux' else types[symbol]
   if owner!='vmlinux':row['edges'].add(owner)
   require(not(symbol.startswith('qdrv_f367r9') and name=='wlan'),'new peer->qdrv trace dependency')
   audited.append(dict(consumer=name,symbol=symbol,owner=owner,export_type=typ))
 pending=set(modules);order=[]
 while pending:
  available=sorted(n for n in pending if not modules[n]['edges']&pending);require(available,'module cycle '+str(pending));order+=available;pending-=set(available)
 tainted={n for n,r in modules.items() if r['info'].get('license') not in ('GPL','GPL v2','Dual BSD/GPL','Dual MIT/GPL')}
 while True:
  new=tainted|{n for n,r in modules.items() if r['edges']&tainted}
  if new==tainted:break
  tainted=new
 for row in audited:require(not(row['consumer'] in tainted and 'GPL' in row['export_type']),'GPL-only taint conflict '+str(row))
 for name,row in modules.items():row['edges']=sorted(row['edges']);row['proprietary_taint']=name in tainted
 for name in ('qdrv','wlan'):
  require(set(modules[name]['exports'])==set(reuse['modules'][name]['exports']),'export API changed '+name)
 artifacts={name:item(out/'a'/(name+'.ko')) for name in ('qdrv','wlan')}
 for name in ('provider','engine','profile'):
  record=reuse['artifacts'][name];require(sha(record['path'])==record['sha256'],'reused binary drift '+name);artifacts[name]=record
 input_pins={str((SOURCE/name).resolve()):digest for name,digest in source['source_pins'].items()};input_pins.update(source['overlay_pins']);input_pins.update(source['patch_sources'])
 for proof in (test,host_test):input_pins.update(proof['source_pins'])
 for peer_source in (SOURCE/'wlan').glob('*.c'):
  for include in re.findall(r'^\s*#include\s+"(\.\./qdrv/[^"\n]+)"',peer_source.read_text(),re.M):
   path=(ROOT/'work/linux510-radio-port/quantenna/wlan'/include).resolve();input_pins[str(path)]=sha(path)
 for p in (Path(__file__),SOURCE/'source-manifest.json',TEST,HOST_TEST,BASE/'manifest.json',KERNEL,REUSE,PEER_CMD):input_pins[str(p.resolve())]=sha(p)
 for p,digest in input_pins.items():require(sha(p)==digest,'input changed during build '+p)
 result=dict(schema='openmitrastar.f367r9-transition-components/v1',status='PASS_F367R9_TRANSITION_OBSERVATION_COMPONENTS',artifacts=artifacts,reproducible=True,source_manifest=item(SOURCE/'source-manifest.json'),source_pins=source['source_pins'],peer_source_pins={n:h for n,h in source['source_pins'].items() if n.startswith('wlan/')},input_pins=input_pins,transition_observation_test=item(TEST),hostlink_trace_test=item(HOST_TEST),modules=modules,imports_audited=audited,load_order=order,changed_modules=['wlan','qdrv'],new_cross_module_trace_symbols=False,peer_parent_flags=parent_flags,kernel_config_sha256=sha(kernel['artifacts']['f363.config']['path']),kernel_vmlinux_sha256=sha(kernel['artifacts']['f363.vmlinux']['path']),kernel_recompiled=False,no_policy_or_timeout_change=True,diagnostic_only=True,hardware_actions=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),status=result['status'],artifacts=artifacts,module_count=len(modules),imports=len(audited)),indent=2))
if __name__=='__main__':main()
