"""Package a disabled F332 module candidate with an audited dependency graph.

No device, flash, host settings, or executable startup action is performed.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,re,shutil
from elftools.elf.elffile import ELFFile
from f331_oem_postfilter_projection import require
ROOT=Path(__file__).resolve().parents[1]
BASE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
BUNDLE=BASE/'f332-kernel-bundle-20260921T121717Z'
PEERS=BASE/'f332-peers-20260921T121519Z'
PRE=BASE/'f330-kernel-preprocess-20260921T103900Z'
POST=BASE/'f331-kernel-20260921T103722Z'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module_info(p):
 with p.open('rb') as f:
  e=ELFFile(f);items=e.get_section_by_name('.modinfo').data().decode().split('\0')
  info={x.split('=',1)[0]:x.split('=',1)[1] for x in items if '=' in x}
  info['exports']=[s.name[len('__ksymtab_'):] for s in e.get_section_by_name('.symtab').iter_symbols() if s.name.startswith('__ksymtab_')]
  info['imports']=[s.name for s in e.get_section_by_name('.symtab').iter_symbols() if s['st_shndx']=='SHN_UNDEF' and s.name]
  return info
def main():
 raise SystemExit('NO_GO: F332 kernel bundle combines Proprietary engines and GPL-only imports. Preserve artifacts for offline analysis; resolve architecture and rerun the real loader audit before packaging.')
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--qdrv-module',type=Path,required=True);ap.add_argument('--qdrv-proof',type=Path,required=True);args=ap.parse_args()
 bundle=json.loads((BUNDLE/'result.json').read_text());peers=json.loads((PEERS/'result.json').read_text());qproof=json.loads(args.qdrv_proof.read_text())
 require(bundle['status']=='PASS_OFFLINE_KERNEL_BUNDLE' and peers['status']=='PASS_COHERENT_PEERS_OFFLINE','unqualified input bundle')
 require(str(qproof.get('status','')).startswith('PASS'),'qdrv proof not PASS')
 out=BASE/('f332-module-candidate-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);(out/'modules').mkdir();(out/'evidence').mkdir()
 inputs=[]
 for row in peers['modules']:
  p=PEERS/'a'/row['name'];require(sha(p)==row['sha256'],'peer artifact drift');inputs.append(p)
 for row in bundle['artifacts'].values():
  p=Path(row['path']);require(sha(p)==row['sha256'],'bundle artifact drift');inputs.append(p)
 for parent in (PRE,POST):
  proof=json.loads((parent/'result.json').read_text());row=proof['module'];p=Path(row['path']);require(sha(p)==row['sha256'],'math module drift');inputs.append(p)
 inputs.append(args.qdrv_module.resolve());nodes={};rows=[]
 for p in inputs:
  info=module_info(p);name=info['name'];require(re.fullmatch(r'[A-Za-z0-9_]+',name),'invalid module identity');require(name not in nodes,'duplicate module name')
  require(info.get('vermagic')=='5.10.260-openmitrastar-radiohw mod_unload ARC700','wrong kernel ABI identity')
  deps=[x for x in info.get('depends','').split(',') if x];require(all(re.fullmatch(r'[A-Za-z0-9_]+',d) for d in deps),'invalid dependency identity');nodes[name]=set(deps)
  destination=out/'modules'/(name+'.ko');shutil.copyfile(p,destination)
  rows.append({'name':name,'file':'modules/'+destination.name,'sha256':sha(destination),'bytes':destination.stat().st_size,'license':info['license'],'depends':deps,'exports':info['exports'],'imports':info['imports']})
 required_new={'radar_set_scan_context','radar_ready_generation','radar_wait_stopped'}
 provider=next(r for r in rows if r['name']=='qtn_radar_f332');require(required_new<=set(provider['exports']),'provider readiness ABI missing')
 qdrv=next(r for r in rows if r['name']=='qdrv');require('qtn_radar_f332' in qdrv['depends'],'qdrv not linked to new provider')
 require(required_new<=set(qdrv['imports']),'qdrv has no ready-generation/scan/drain integration')
 missing=set().union(*nodes.values())-nodes.keys();require(not missing,'missing module dependencies: '+str(missing))
 order=[];remaining={n:set(d) for n,d in nodes.items()}
 while remaining:
  ready=sorted(n for n,deps in remaining.items() if not deps)
  require(ready,'dependency cycle: '+str(remaining))
  order.extend(ready)
  for n in ready:del remaining[n]
  for deps in remaining.values():deps.difference_update(ready)
 evidence=[BUNDLE/'result.json',PEERS/'result.json',PRE/'result.json',POST/'result.json',args.qdrv_proof.resolve(),BASE/'f332-peer-abi-20260921T121907Z/result.json',BASE/'f332-ocac-20260921T113817Z/result.json',BASE/'f333-acquisition-20260921T110904Z/result.json',ROOT/'outputs/preflight/f332-startup-20260921T120146Z/result.json',ROOT/'outputs/preflight/f332-lifetime-20260921T121659Z/result.json']
 records=[]
 for index,p in enumerate(evidence):
  name=f'{index:02d}-{p.parent.name}-{p.name}';shutil.copyfile(p,out/'evidence'/name);records.append({'original':str(p),'file':'evidence/'+name,'sha256':sha(p)})
 shutil.copyfile(ROOT/'docs/OPENMITRASTAR_F332_PIPELINE_INTEGRATION.md',out/'PIPELINE.md')
 manifest={'schema':'openmitrastar.f332-disabled-module-candidate/v1','status':'PASS_OFFLINE_MODULE_CANDIDATE_PHYSICAL_UNRUN','created_utc':datetime.now(timezone.utc).isoformat(),'target':'HGW-500BNA-QCv2 A2','kernel':'5.10.260-openmitrastar-radiohw','kernel_config_sha256':'cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e','modules':rows,'dependency_order':order,'provider_parameters':{'hardware_enable':False,'diagnostic_capture':False,'authoritative_enable':False},'calibration_loader_parameters':'Must retain exact existing device-bound startup and calibration inputs; graph order alone is not a loader','evidence':records,'qdrv_module_sha256':sha(args.qdrv_module),'qdrv_proof_sha256':sha(args.qdrv_proof),'hardware_actions':False,'flash_image_created':False,'startup_executed':False,'physical_acceptance':False,'dfs_rf_acceptance':False,'release_eligible':False}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (out/'LOAD_PLAN.md').write_text('# F332 module candidate, disabled\n\nThis is a module dependency plan, not an executable startup script or flash image. Preserve the accepted device-bound calibration/identity loader.\n\nOrder:\n\n'+''.join(f'{i+1}. `{n}`\n' for i,n in enumerate(order))+'\nProvider parameters are hardware_enable=0, diagnostic_capture=0, authoritative_enable=0. Root owns all physical gates.\n')
 (out/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.relative_to(out).as_posix()+'\n' for p in sorted(out.rglob('*')) if p.is_file()))
 print(json.dumps({'output':str(out),'status':manifest['status'],'modules':len(rows),'dependency_order':order},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
