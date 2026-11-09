"""Seal the disabled F338 module/service bundle with a real loader graph audit."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import require
ROOT=Path(__file__).resolve().parents[1]
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
PEERS=BASE/'f332-peers-20260921T121519Z'
PIPE=BASE/'f338-pipeline-20260921T132141Z/result.json'
IPC=ROOT/'outputs/preflight/f338-ipc-20260921T131909Z/result.json'
LIFE=ROOT/'outputs/preflight/f338-lifetime-20260921T131728Z/result.json'
USER=BASE/'f338-service-20260921T132141Z/result.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def info(path):
 with path.open('rb') as f:
  elf=ELFFile(f);fields=elf.get_section_by_name('.modinfo').data().decode().split('\0')
  values=dict(x.split('=',1) for x in fields if '=' in x)
  symbols=list(elf.get_section_by_name('.symtab').iter_symbols())
  imports={s.name for s in symbols if s.name and s['st_shndx']=='SHN_UNDEF'}
  exports={s.name[10:] for s in symbols if s.name.startswith('__ksymtab_')}
 return values,imports,exports
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--kernel-result',required=True,type=Path);ap.add_argument('--qdrv-manifest',required=True,type=Path);a=ap.parse_args()
 kernel=json.loads(a.kernel_result.read_text());qdrv=json.loads(a.qdrv_manifest.read_text());peers=json.loads((PEERS/'result.json').read_text());service=json.loads(USER.read_text());pipeline=json.loads(PIPE.read_text());ipc=json.loads(IPC.read_text());lifetime=json.loads(LIFE.read_text())
 require(kernel['status']=='PASS_OFFLINE_GPL_KERNEL_BUILD','kernel not qualified');require(qdrv['status'].startswith('PASS_'),'qdrv not qualified');require(peers['status']=='PASS_COHERENT_PEERS_OFFLINE','peers unqualified');require(service['status']=='PASS_STATIC_SERVICE_BUILD','service unqualified');require(pipeline['status']=='PASS_COMPOSITION_VS_F332_ORACLE','pipeline unqualified');require(ipc['status']=='PASS_ACTUAL_C_IPC_THREADS','IPC unqualified');require(lifetime['status']=='PASS_ACTUAL_F338_LIFETIME','lifetime unqualified')
 for rel,digest in kernel['sources'].items():require(sha(ROOT/rel)==digest,'kernel source drift '+rel)
 require(sha(ROOT/'work/kernel-port/f338/kernel/f338_ipc.c')==ipc['source_sha256'],'IPC changed after test')
 require(sha(ROOT/'work/kernel-port/f338/kernel/f332_provider.c')==lifetime['provider_sha256'],'lifetime source drift')
 old_backend=(ROOT/'work/kernel-port/modules/f332_dfs_provider/provider/f332_hardware.c').read_text()
 expected_backend=old_backend.replace('f332_pipeline.h','f338_pipeline.h').replace('OMF332','OMF338')
 require((ROOT/'work/kernel-port/f338/kernel/f332_hardware.c').read_text()==expected_backend,'native hardware sequence changed after F332 oracle')
 for name in ('f332_setup.inc','f332_ocac.c','f332_ocac.h','f332_events.c','f332_events.h','f327_oem_requests.h'):
  require((ROOT/'work/kernel-port/f338/kernel'/name).read_bytes()==(ROOT/'work/kernel-port/modules/f332_dfs_provider/provider'/name).read_bytes(),'reused GPL component drift '+name)
 for group,names in (('f333_acquisition',('f333_acquisition.c','f333_acquisition.h')),('f331_postfilter',('f331_postfilter.c','f331_postfilter.h'))):
  for name in names:require((ROOT/'work/kernel-port/f338/kernel'/name).read_bytes()==(ROOT/'work/kernel-port/modules'/group/name).read_bytes(),'oracle component drift '+name)
 for rel,digest in service['sources'].items():require(sha(ROOT/'work/kernel-port/f338'/rel)==digest,'service source drift '+rel)
 for rel,digest in pipeline['sources'].items():
  if rel.startswith(('userspace','uapi')) or rel in ('kernel\\f338_pipeline.c','kernel\\f338_pipeline.h','kernel\\f331_postfilter.c','kernel\\f331_postfilter.h'):
   require(sha(ROOT/'work/kernel-port/f338'/rel)==digest,'math composition drift '+rel)
 out=BASE/('f338-provider-bundle-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);(out/'modules').mkdir();(out/'bin').mkdir()
 inputs=[(PEERS/'a'/row['name'],row['sha256']) for row in peers['modules']]
 inputs.extend((Path(report['artifact']['path']),report['artifact']['sha256']) for report in (kernel,qdrv))
 modules={};symbol_owners={};errors=[]
 for source,digest in inputs:
  require(sha(source)==digest,'artifact drift '+str(source));values,imports,exports=info(source);name=values['name'];dest=out/'modules'/(name+'.ko');dest.write_bytes(source.read_bytes())
  require(name not in modules,'duplicate module '+name)
  license=values.get('license','');gpl=license in ('GPL','GPL v2','GPL and additional rights','Dual BSD/GPL','Dual MIT/GPL','Dual MPL/GPL')
  modules[name]={'file':str(dest),'sha256':digest,'bytes':dest.stat().st_size,'license':license,'gpl_compatible':gpl,'declared_dependencies':list(filter(None,values.get('depends','').split(','))),'imports':sorted(imports),'exports':sorted(exports),'edges':set()}
  for symbol in exports:
   if symbol in symbol_owners:errors.append('duplicate export '+symbol)
   symbol_owners[symbol]=name
  if not values.get('vermagic','').startswith('5.10.260-openmitrastar-radiohw'):errors.append('ABI mismatch '+name)
 vmlinux=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.vmlinux'
 require(sha(vmlinux)=='8d7a81947e43f2e9763e0228347802fb008956c754431e75e0db0b66e73d7fbc','kernel identity drift')
 with vmlinux.open('rb') as f:
  elf=ELFFile(f);kernel_exports={s.name[10:] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name.startswith('__ksymtab_')}
 symvers={}
 for path in (a.kernel_result.parent/'kernel.symvers',PEERS/'Module-a.symvers',a.kernel_result.parent/'a/kernel/Module.symvers',a.qdrv_manifest.parent/'qdrv-a-Module.symvers'):
  for line in path.read_text().splitlines():
   bits=line.split();symvers[bits[1]]=bits[3]
 audited=[]
 for name,row in modules.items():
  for symbol in row['imports']:
   if symbol in kernel_exports:owner='vmlinux'
   elif symbol in symbol_owners:owner=symbol_owners[symbol];row['edges'].add(owner)
   else:errors.append(name+' unresolved '+symbol);continue
   if symbol not in symvers:errors.append('export type unavailable '+symbol)
   audited.append({'consumer':name,'symbol':symbol,'owner':owner,'export_type':symvers.get(symbol),'owner_gpl_compatible':owner=='vmlinux' or modules[owner]['gpl_compatible']})
  for dep in row['declared_dependencies']:
   if dep not in modules:errors.append(name+' missing declared dependency '+dep)
   else:row['edges'].add(dep)
 order=[];pending=set(modules)
 while pending:
  available=sorted(n for n in pending if not (modules[n]['edges']&pending))
  if not available:errors.append('loader dependency cycle '+','.join(sorted(pending)));break
  order.extend(available);pending.difference_update(available)
 for row in modules.values():row['edges']=sorted(row['edges'])
 # Linux5.10 inherit_taint follows imported module ownership, not the
 # machine's global taint. Preserve the proprietary baseline FWT module:
 # it must not consume GPL-only symbols or taint such a consumer transitively.
 tainted={name for name,row in modules.items() if not row['gpl_compatible']}
 while True:
  inherited={name for name,row in modules.items() if any(owner in tainted for owner in row['edges'])}
  expanded=tainted|inherited
  if expanded==tainted:break
  tainted=expanded
 for name,row in modules.items():
  row['proprietary_taint']=name in tainted
  row['taint_from']=[owner for owner in row['edges'] if owner in tainted]
 for row in audited:
  if row['consumer'] in tainted and row['export_type'] and 'GPL' in row['export_type']:errors.append('Linux5.10 GPL-only/proprietary conflict '+row['consumer']+' -> '+row['symbol'])
 require(not any(n.startswith(('f328','f330','f332_detector')) for n in modules),'proprietary engine kernel module included')
 binary=Path(service['binary']['path']);require(sha(binary)==service['binary']['sha256'],'service binary drift');(out/'bin/om-radar-engine-f338').write_bytes(binary.read_bytes())
 (out/'f338_uapi.h').write_bytes((ROOT/'work/kernel-port/f338/uapi/f338_uapi.h').read_bytes())
 (out/'STARTUP-SHUTDOWN.md').write_bytes((ROOT/'docs/OPENMITRASTAR_F338_KERNEL_USERSPACE_DFS.md').read_bytes())
 for path in (a.kernel_result,a.qdrv_manifest,USER,PIPE,IPC,LIFE,PEERS/'result.json'):
  target=out/(path.parent.name+'-'+path.name);target.write_bytes(path.read_bytes())
 result={'schema':'openmitrastar.f338-provider-bundle/v1','status':'PASS_DISABLED_BUNDLE_OFFLINE' if not errors else 'NO_GO','errors':errors,'modules':modules,'load_order':order,'imports_audited':audited,'proprietary_taint_modules':sorted(tainted),'service':service['binary'],'kernel_vmlinux_sha256':sha(vmlinux),'kernel_config_sha256':kernel['config_sha256'],'kernel_loader_source_sha256':sha(a.kernel_result.parent/'kernel-module.c'),'legacy_kernel_taint_checks_preserved':True,'hardware_enable_default':False,'diagnostic_capture_default':False,'authoritative_enable_default':False,'release_qualified':False,'firmware_built':False,'hardware_executed':False,'private_OEM_userspace_objects':True,'real_ARC_math_gate':str(ROOT/'outputs/handoff-live/f338-ram-math-20260921T130615Z/result.json')}
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'manifest':str(out/'manifest.json'),'status':result['status'],'errors':errors,'modules':len(modules),'imports':len(audited),'load_order':order},indent=2));return bool(errors)
if __name__=='__main__':raise SystemExit(main())
