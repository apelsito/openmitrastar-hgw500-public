"""Build native F366 provider/qdrv against F365's actual kernel and peer modules."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shlex,shutil,subprocess
from elftools.elf.elffile import ELFFile
import f334_qdrv_contract as qc
import build_f338_qdrv_availability as readiness
ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
SOURCE=ROOT/'work/kernel-port/f367r7-clock-publication'
BASE=DEVICE/'firmware/f365-f364r3-temperature-data-device-bound'
COMP=Path('/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/result.json')
ENGINE=DEVICE/'analysis/f338-service-20260921T132141Z/a/om-radar-engine-f338'
REUSE=ROOT/'outputs/kernel-port/f367r5-qualified-20260922T174654Z/result.json'
STATIC=ROOT/'outputs/kernel-port/f367r6-static-qualified-20260922T183736Z/result.json'
ACK_TEST=ROOT/'outputs/preflight/f367r7-clock-publication-20260922T193631Z/result.json'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def require(v,m):
 if not v:raise ValueError(m)
def item(p):p=Path(p);return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
def inspect(p):
 with Path(p).open('rb') as f:
  e=ELFFile(f);s=list(e.get_section_by_name('.symtab').iter_symbols());info=dict(v.split('=',1) for v in e.get_section_by_name('.modinfo').data().decode().split('\0') if '=' in v)
  imports={x.name for x in s if x.name and x['st_shndx']=='SHN_UNDEF'};exports={x.name[10:] for x in s if x.name.startswith('__ksymtab_')}
  types={x:'EXPORT_SYMBOL_GPL' if any(y.name=='__kstrtabns_'+x and False for y in s) else 'EXPORT_SYMBOL' for x in exports}
  for sec in e.iter_sections():
   if sec.name.startswith('___ksymtab_gpl+'):types[sec.name.split('+',1)[1]]='EXPORT_SYMBOL_GPL'
  return info,imports,exports,types
def main():
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 require(sha(BASE/'manifest.json')=='a73a41e32d793a33ec13c46ef62bbf5890039339d38ef107d04c13b91e19d19c','F365 manifest changed')
 require(sha(COMP)=='5036e7a5980a22c81c08506c1a77ba1af7ec3ceeeab69393e2d0bfdbb6d7bdf3','F363 component evidence changed')
 source=json.loads((SOURCE/'source-manifest.json').read_text());base=json.loads((BASE/'manifest.json').read_text());comp=json.loads(COMP.read_text())
 reuse=json.loads(REUSE.read_text());test=json.loads(ACK_TEST.read_text())
 require(reuse['status']=='PASS_F367R5_REGULATORY_BUILD_LINK_AND_REPRODUCTION' and test['status']=='PASS_F367R7_DUAL_CLOCK_PUBLICATION','R4 dependencies not qualified')
 for path,digest in test['source_pins'].items():require(sha(path)==digest,'clock test source drift')
 static=json.loads(STATIC.read_text());require(static['status']=='PASS_OFFLINE_F367R6_STATIC_PROFILE','static helper unqualified')
 require(sha(static['artifact']['path'])==static['artifact']['sha256'],'static helper drift')
 require(test['admission_guard_unchanged'] in (SOURCE/'qdrv/qdrv/qdrv_f367_control.inc').read_text(),'admission predicate changed')
 for name,digest in source['source_pins'].items():
  if name!='qdrv/qdrv/qdrv_f367_control.inc':require(reuse['source_pins'].get(name)==digest,'unrelated R4 source change '+name)
 require(sha(reuse['artifacts']['provider']['path'])==reuse['artifacts']['provider']['sha256'],'reused provider drift')
 proof=source['physical_prerequisite'];require(sha(proof['path'])==proof['sha256']=='9201514a074decb9987cdaa174f25c19739ddc083e9a842179fec77cc633fb87','exact physical R3 prerequisite required')
 evidence=json.loads(Path(proof['path']).read_text());require(evidence['status']=='PASS_F366R3_NATIVE_ACQUISITION_WITH_F365_RETURN_ADDENDUM','R3 acquisition not accepted')
 for path,digest in evidence['evidence'].items():require(sha(path)==digest,'R3 evidence drift')
 for n,h in source['source_pins'].items():require(sha(SOURCE/n)==h,'F366 source drift '+n)
 require(sha(ENGINE)=='737cbdfeb429caba42929374c4a22eab549791c6af42fb3149c5ad64c048c85b','qualified engine drift')
 rootfs=BASE/base['artifacts']['rootfs_squashfs']['file'];require(sha(rootfs)==base['artifacts']['rootfs_squashfs']['sha256'],'F365 rootfs drift')
 config=Path(comp['artifacts']['f363.config']['path']);vmlinux=Path(comp['artifacts']['f363.vmlinux']['path'])
 sidecar=BASE/(base['artifacts']['webformat']['file'].removesuffix('.webformat.bin')+'.vmlinux')
 require(sha(config)==base['artifacts']['config']['sha256'] and sha(vmlinux)==sha(sidecar),'F365 kernel/source ABI mismatch')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=Path('/workspace/OpenMitraStar-build/f367r7')/('f367r7-clock-'+stamp);out.mkdir(parents=True,exist_ok=False)
 for sub in ('qdrv','kernel','uapi'):shutil.copytree(SOURCE/sub,out/'source'/sub)
 for path,digest in {**source['userspace_pins'],**source['producer_and_layout_pins']}.items():require(sha(path)==digest,'OEM producer/layout drift')
 deps=Path(comp['completed_build'])/'a/dependencies.symvers';shutil.copyfile(deps,out/'peers.symvers');shutil.copyfile(Path(comp['artifacts']['Module.symvers']['path']),out/'kernel.symvers')
 # The unchanged readiness/lifetime source and R4 machine-code qualification are reused.
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');gpl=linux(ROOT/'work/sources/Quantenna-GPL');build='/home/user/openmitrastar-build/f367r7-clock-'+stamp
 script=f'''set -eu
out={q(linux(out))}
build={q(build)}
src={q(comp['kernel_source_linux'])}
tc={q(tc)}
test ! -e "$build"
mkdir "$build"
cp -a --reflink=auto {q(comp['kernel_build_directory_linux'])} "$build/kernel-context"
kout="$build/kernel-context"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {sha(config)}
unsquashfs -processors 1 -no-progress -d "$out/baseline-rootfs" {q(linux(rootfs))} > "$out/extract.log"
for lane in a b; do
 cp -a "$out/source" "$build/$lane"
 cp {q(linux(Path(reuse['artifacts']['provider']['path']).parent/'provider.symvers'))} "$build/$lane/kernel/Module.symvers"
 cp {q(linux(reuse['artifacts']['provider']['path']))} "$build/$lane/kernel/qtn_radar_f367.ko"
 cat "$out/peers.symvers" "$build/$lane/kernel/Module.symvers" > "$build/$lane/native-dependencies.symvers"
 SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$build/$lane/qdrv" QTN_GPL={q(gpl)} KBUILD_EXTRA_SYMBOLS="$build/$lane/native-dependencies.symvers" KCFLAGS="-ffile-prefix-map=$build/$lane=/f366-source" -j4 modules > "$out/qdrv-$lane.log" 2>&1
 mkdir "$out/$lane"
 cp "$build/$lane/kernel/qtn_radar_f367.ko" "$out/$lane/"
 cp "$build/$lane/qdrv/qdrv/qdrv.ko" "$out/$lane/"
 cp "$build/$lane/kernel/Module.symvers" "$out/$lane/provider.symvers"
 cp "$build/$lane/qdrv/Module.symvers" "$out/$lane/qdrv.symvers"
done
cmp "$out/a/qtn_radar_f367.ko" "$out/b/qtn_radar_f367.ko"
cmp "$out/a/qdrv.ko" "$out/b/qdrv.ko"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {sha(config)}
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware_actions':False}),flush=True)
 run=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
 (out/'stdout').write_bytes(run.stdout);(out/'stderr').write_bytes(run.stderr);require(run.returncode==0,'F366 build failed; evidence '+str(out))
 modules={};owners={};types={};kernel_exports={}
 for line in (out/'kernel.symvers').read_text().splitlines():b=line.split();kernel_exports[b[1]]=b[3]
 for p in sorted((out/'baseline-rootfs/lib/modules').rglob('*.ko')):
  info,imports,exports,et=inspect(p)
  if info['name']=='qdrv':continue
  modules[info['name']]={**item(p),'info':info,'imports':sorted(imports),'exports':sorted(exports),'edges':set()}
  for symbol in exports:require(symbol not in owners,'duplicate baseline export '+symbol);owners[symbol]=info['name'];types[symbol]=et[symbol]
 for p in (out/'a/qtn_radar_f367.ko',out/'a/qdrv.ko'):
  info,imports,exports,et=inspect(p);modules[info['name']]={**item(p),'info':info,'imports':sorted(imports),'exports':sorted(exports),'edges':set()}
  for symbol in exports:require(symbol not in owners and symbol not in kernel_exports,'duplicate native export '+symbol);owners[symbol]=info['name'];types[symbol]=et[symbol]
 for path in (out/'peers.symvers',out/'a/provider.symvers',out/'a/qdrv.symvers'):
  for line in path.read_text().splitlines():b=line.split();types[b[1]]=b[3]
 audited=[]
 for name,row in modules.items():
  for symbol in row['imports']:
   owner='vmlinux' if symbol in kernel_exports else owners.get(symbol);require(owner is not None,'unresolved '+name+':'+symbol)
   typ=kernel_exports[symbol] if owner=='vmlinux' else types[symbol]
   if owner!='vmlinux':row['edges'].add(owner)
   audited.append({'consumer':name,'symbol':symbol,'owner':owner,'export_type':typ})
 pending=set(modules);order=[]
 while pending:
  available=sorted(n for n in pending if not modules[n]['edges']&pending);require(available,'module cycle '+str(pending));order+=available;pending-=set(available)
 tainted={n for n,r in modules.items() if r['info'].get('license') not in ('GPL','GPL v2','Dual BSD/GPL','Dual MIT/GPL')}
 while True:
  new=tainted|{n for n,r in modules.items() if r['edges']&tainted}
  if new==tainted:break
  tainted=new
 for row in audited:require(not(row['consumer'] in tainted and 'GPL' in row['export_type']),'GPL-only taint conflict '+str(row))
 require('qdrv' not in tainted and 'qtn_radar_f367' not in tainted,'native path tainted')
 for name,row in modules.items():row['edges']=sorted(row['edges']);row['proprietary_taint']=name in tainted
 baseline=out/'baseline-rootfs/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'
 profile=qc.inspect(out/'a/qdrv.ko')
 for parameter,mode in [('openmitrastar_native_radar_diagnostic',0o400),('openmitrastar_dfs_state',0o400),('openmitrastar_dfs_control',0o200)]:require(profile['parameters'].pop(parameter,None)==mode,'new control parameter profile mismatch '+parameter)
 qc.assert_profile(profile,qc.inspect(baseline))
 before=qc.normalized_functions(baseline);after=qc.normalized_functions(out/'a/qdrv.ko')
 protected=['qdrv_get_internal_temp','qdrv_wps_button_read',*[n for n in before if n.startswith('qdrv_f355_')]]
 for name in protected:require(before.get(name)==after.get(name),'retained lifetime/thermal/WPS machine code changed '+name)
 for n,h in source['source_pins'].items():require(sha(SOURCE/n)==h,'source changed during build '+n)
 result={'schema':'openmitrastar.f367r7-clock-component/v1','status':'PASS_F367R7_CLOCK_COMPONENTS','source_manifest':item(SOURCE/'source-manifest.json'),'source_pins':source['source_pins'],'baseline_manifest':item(BASE/'manifest.json'),'kernel_config_sha256':sha(config),'kernel_vmlinux_sha256':sha(vmlinux),'kernel_recompiled':False,'artifacts':{'qdrv':item(out/'a/qdrv.ko'),'provider':item(out/'a/qtn_radar_f367.ko'),'engine':item(ENGINE),'profile':static['artifact']},'modules':modules,'imports_audited':audited,'load_order':order,'reproducible':True,'readiness_tests':reuse['readiness_tests'],'shutdown_tests':reuse['shutdown_tests'],'reused_r4_component':item(REUSE),'regulatory_test':reuse['regulatory_test'],'clock_test':item(ACK_TEST),'static_profile_qualification':item(STATIC),'userspace_pins':source['userspace_pins'],'producer_and_layout_pins':source['producer_and_layout_pins'],'source_contract_checks':24,'protected_functions_byte_equivalent':protected,'f355_lifetime_preserved':True,'authority_compiled_off':False,'authority_build':1,'functional_tests_required_before_composition':True,'hardware_actions':False,'physical_gates':'UNRUN_ACQUISITION_RF_CAC_NOP_CLIENT_SOAK','isolated_build':build}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'artifacts':result['artifacts'],'imports':len(audited),'modules':len(modules)}))
if __name__=='__main__':main()
