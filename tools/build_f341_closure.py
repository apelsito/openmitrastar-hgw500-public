"""Recompile all26 F341 radio modules against the exact isolated F340 kernel."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shlex,shutil,subprocess
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import linux,require
ROOT=Path(__file__).resolve().parents[1]
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
PEERS=BASE/'f332-peers-20260921T121519Z'
QDRV=ROOT/'work/linux510-radio-port/quantenna-f338-availability'
QDRV_PROOF=ROOT/'outputs/kernel-port/f338-qdrv-availability-20260921T132134Z/manifest.json'
SOURCE=ROOT/'work/kernel-port/f341'
ENGINE=BASE/'f338-service-20260921T132141Z/a/om-radar-engine-f338'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def elf_info(path):
 with path.open('rb') as f:
  e=ELFFile(f);values=dict(v.split('=',1) for v in e.get_section_by_name('.modinfo').data().decode().split('\0') if '=' in v)
  symbols=list(e.get_section_by_name('.symtab').iter_symbols());imports={s.name for s in symbols if s['st_shndx']=='SHN_UNDEF' and s.name};exports={s.name[10:] for s in symbols if s.name.startswith('__ksymtab_')}
 return values,imports,exports
def copytree_files(src,dst):
 dst.mkdir(parents=True)
 for p in src.rglob('*'):
  if p.is_symlink():raise ValueError('source symlink '+str(p))
  if p.is_file():q=dst/p.relative_to(src);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--f340-kernel-result',required=True,type=Path);a=ap.parse_args()
 kernel=json.loads(a.f340_kernel_result.read_text());require(kernel['status']=='PASS_OFFLINE_WATCHDOG_KERNEL_UNARMED','F340 kernel not qualified')
 kd=a.f340_kernel_result.parent;config=kd/'a/f340.config';vmlinux=kd/'a/f340.vmlinux';require(config.exists() and vmlinux.exists(),'F340 sidecars missing')
 peers=json.loads((PEERS/'result.json').read_text());require(peers['status']=='PASS_COHERENT_PEERS_OFFLINE','peer source not qualified')
 for rel,digest in peers['sources'].items():require(sha(PEERS/'source'/rel)==digest,'peer source drift '+rel)
 qproof=json.loads(QDRV_PROOF.read_text());require(qproof['status']=='PASS_OFFLINE_AVAILABILITY_HANDSHAKE_AND_LIFETIME','qdrv readiness source not qualified')
 for row in qproof['sources']:require(sha(ROOT/row['path'])==row['sha256'],'qdrv source drift '+row['path'])
 require(sha(ENGINE)=='737cbdfeb429caba42929374c4a22eab549791c6af42fb3149c5ad64c048c85b','real-ARC-qualified engine drift')
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=BASE/('f341-closure-'+stamp);out.mkdir(parents=True,exist_ok=False)
 copytree_files(SOURCE/'kernel',out/'source/provider');copytree_files(SOURCE/'uapi',out/'source/uapi');copytree_files(PEERS/'source',out/'source/peers')
 for sub in ('qdrv','wlan','mtest'):
  if (QDRV/sub).exists():copytree_files(QDRV/sub,out/'source/qdrv'/sub)
 (out/'source/qdrv/Makefile').write_bytes((QDRV/'Makefile').read_bytes())
 sources={str(p.relative_to(out/'source')):sha(p) for p in (out/'source').rglob('*') if p.is_file()}
 (out/'qdrv-exports.symvers').write_bytes((QDRV_PROOF.parent/'qdrv-a-Module.symvers').read_bytes())
 platform=[line for line in (PEERS/'Module-a.symvers').read_text().splitlines() if line.split()[1] in ('soc_shared_params','get_bootcfg_scancnt')];require(len(platform)==2,'platform ownership ambiguous')
 (out/'platform.symvers').write_bytes(('\n'.join(platform)+'\n').encode())
 (out/'kernel.config').write_bytes(config.read_bytes());(out/'kernel.symvers').write_bytes((kd/'a/Module.symvers').read_bytes())
 q=shlex.quote;tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-');qtn=linux(ROOT/'work/sources/Quantenna-GPL')
 ksource=kernel['isolated_build']+'/linux';koriginal=(kd/'a/build-directory.txt').read_text().strip();module_kout='/home/user/openmitrastar-build/f341-module-context-'+stamp
 script=f'''set -eu
out={q(linux(out))}
tc={q(tc)}
src={q(ksource)}
kout={q(module_kout)}
test ! -e "$kout"
cp -a --reflink=auto {q(koriginal)} "$kout"
SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f340-watchdog-baseline KBUILD_BUILD_VERSION=340 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" modules_prepare > "$out/modules-prepare.log" 2>&1
cp "$out/kernel.symvers" "$kout/Module.symvers"
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {sha(config)}
for lane in a b; do
 mkdir "$out/$lane"
 cp -a "$out/source"/. "$out/$lane/"
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f341-native KBUILD_BUILD_VERSION=341 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/provider" QTN_GPL={q(qtn)} QDRV_COMPAT="$out/$lane/qdrv/qdrv/compat/include" KBUILD_EXTRA_SYMBOLS="$out/platform.symvers" KCFLAGS="-ffile-prefix-map=$out/$lane=/f341-source" -j4 modules > "$out/provider-$lane.log" 2>&1
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f341-native KBUILD_BUILD_VERSION=341 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/peers" QTN_GPL={q(qtn)} QDRV_COMPAT="$out/$lane/peers/qdrv/compat/include" OPENMITRASTAR_QDRV_V89_PAIR=1 OPENMITRASTAR_SWITCH_EMAC_PORT=1 KBUILD_EXTRA_SYMBOLS="$out/qdrv-exports.symvers" KCFLAGS="-ffile-prefix-map=$out/$lane=/f341-source" -j4 modules > "$out/peers-$lane.log" 2>&1
 cat "$out/$lane/provider/Module.symvers" "$out/$lane/peers/Module.symvers" > "$out/$lane/qdrv-dependencies.symvers"
 SOURCE_DATE_EPOCH=1790006400 KBUILD_BUILD_TIMESTAMP=@1790006400 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=f341-native KBUILD_BUILD_VERSION=341 make -s -C "$src" O="$kout" ARCH=arc CROSS_COMPILE="$tc" M="$out/$lane/qdrv" QTN_GPL={q(qtn)} QDRV_COMPAT="$out/$lane/qdrv/qdrv/compat/include" OPENMITRASTAR_QDRV_V89_PAIR=1 OPENMITRASTAR_SWITCH_EMAC_PORT=1 KBUILD_EXTRA_SYMBOLS="$out/$lane/qdrv-dependencies.symvers" KCFLAGS="-ffile-prefix-map=$out/$lane=/f341-source" -j4 modules > "$out/qdrv-$lane.log" 2>&1
 mkdir "$out/$lane/modules"
 find "$out/$lane/provider" "$out/$lane/peers" "$out/$lane/qdrv" -name '*.ko' -type f -exec cp -t "$out/$lane/modules/" {{}} +
done
for module in "$out/a/modules/"*.ko; do cmp "$module" "$out/b/modules/$(basename "$module")"; done
test "$(sha256sum "$kout/.config" | cut -d' ' -f1)" = {sha(config)}
'''
 (out/'build.sh').write_bytes(script.encode());print(json.dumps({'build_started':str(out),'hardware':False}),flush=True)
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'build.sh')],stdin=subprocess.DEVNULL,capture_output=True)
 (out/'stdout').write_bytes(p.stdout);(out/'stderr').write_bytes(p.stderr)
 errors=[];modules={};owners={};audited=[];order=[]
 if p.returncode:errors.append('closure build or reproducibility failed')
 if not p.returncode:
  for path in sorted((out/'a/modules').glob('*.ko')):
   values,imports,exports=elf_info(path);name=values['name'];license=values.get('license','')
   modules[name]={'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path),'license':license,'gpl_compatible':license in ('GPL','GPL v2','Dual BSD/GPL','Dual MIT/GPL'),'imports':sorted(imports),'exports':sorted(exports),'dependencies':list(filter(None,values.get('depends','').split(','))),'vermagic':values.get('vermagic'),'edges':set()}
   for symbol in exports:
    if symbol in owners:errors.append('duplicate export '+symbol)
    owners[symbol]=name
  if len(modules)!=26 or 'qtn_radar_f341' not in modules:errors.append('expected26 modules including F341 provider')
  with vmlinux.open('rb') as f:kernel_exports={s.name[10:] for s in ELFFile(f).get_section_by_name('.symtab').iter_symbols() if s.name.startswith('__ksymtab_')}
  exports={}
  for path in (out/'kernel.symvers',out/'a/provider/Module.symvers',out/'a/peers/Module.symvers',out/'a/qdrv/Module.symvers'):
   for line in path.read_text().splitlines():bits=line.split();exports[bits[1]]=bits[3]
  for name,row in modules.items():
   for symbol in row['imports']:
    owner='vmlinux' if symbol in kernel_exports else owners.get(symbol)
    if owner is None or symbol not in exports:errors.append('unresolved symbol/export type '+name+':'+symbol);continue
    if owner!='vmlinux':row['edges'].add(owner)
    audited.append({'consumer':name,'symbol':symbol,'owner':owner,'export_type':exports[symbol]})
   for dependency in row['dependencies']:
    if dependency not in modules:errors.append('missing module dependency '+dependency)
    else:row['edges'].add(dependency)
  pending=set(modules)
  while pending:
   available=sorted(n for n in pending if not(modules[n]['edges']&pending))
   if not available:errors.append('module cycle '+','.join(sorted(pending)));break
   order+=available;pending-=set(available)
  tainted={name for name,row in modules.items() if not row['gpl_compatible']}
  while True:
   derived=tainted|{name for name,row in modules.items() if row['edges']&tainted}
   if derived==tainted:break
   tainted=derived
  for name,row in modules.items():row['edges']=sorted(row['edges']);row['proprietary_taint']=name in tainted
  for row in audited:
   if row['consumer'] in tainted and 'GPL' in row['export_type']:errors.append('GPL-only/taint conflict '+row['consumer']+':'+row['symbol'])
 result={'schema':'openmitrastar.f341-closure/v1','status':'PASS_F341_COHERENT_CLOSURE' if not errors else 'FAIL','errors':errors,'kernel_config_sha256':sha(config),'kernel_vmlinux_sha256':sha(vmlinux),'kernel_proof':str(a.f340_kernel_result),'isolated_module_context':module_kout,'source':sources,'modules':modules,'imports_audited':audited,'load_order':order,'engine':{'path':str(ENGINE),'bytes':ENGINE.stat().st_size,'sha256':sha(ENGINE)},'reproducible':not errors,'hardware':False,'wifi_physical':'USER_DEFERRED','watchdog_physical':'PENDING_ROOT_GATE'}
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'manifest':str(out/'manifest.json'),'status':result['status'],'errors':errors,'modules':len(modules)},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
