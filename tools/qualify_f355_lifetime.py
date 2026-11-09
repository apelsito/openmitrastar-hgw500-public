"""Seal the software-only F355 lifetime correction and coherent module set."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,difflib,hashlib,json,shutil,subprocess
import f334_qdrv_contract as elf
from f331_oem_postfilter_projection import linux
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'work/linux510-radio-port/quantenna-f344-modes'
SRC=ROOT/'work/linux510-radio-port/quantenna-f355-lifetime'
BASE_PROOF=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f344-closure-20260921T162003Z/manifest.json'
F344_MANIFEST=ROOT/'outputs/handoff/f344-mode-components-20260921T162648Z/manifest.json'
F344_SHA='fffd6643a7db9f186aefa02e06f29995f8742ad7f91f824a34f8cb80ecf84401'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ('closure','lifetime-test','proc-test'):ap.add_argument('--'+n,type=Path,required=True)
 a=ap.parse_args();before=shutil.disk_usage(ROOT).free;require(before>500*1024*1024,'C: free space guard')
 closure=json.loads(a.closure.read_text());lt=json.loads(a.lifetime_test.read_text());pt=json.loads(a.proc_test.read_text())
 require(closure['status']=='PASS_F355_FINAL_COHERENT_CLOSURE_OFFLINE' and not closure['errors'],'unqualified final closure')
 require(lt['status']=='PASS_ACTUAL_DRIVER_KERNEL_LIFETIME','lifetime test failed');require(pt['status']=='PASS_PROC_INIT_EXIT_AND_RELEASE_CONTRACT' and all(pt['contracts'].values()),'proc/lifetime contract failed')
 pins={name.replace('\\','/'):v for name,v in closure['source'].items()}
 for proof in (lt,pt):
  for name,digest in proof['source_bindings'].items():
   require(sha(SRC/'qdrv'/name)==digest and pins.get('qdrv/qdrv/'+name)==digest,'test/source/built mismatch '+name)
 require(sha(F344_MANIFEST)==F344_SHA,'F344 immutable manifest changed')
 baseproof=json.loads(BASE_PROOF.read_text());baseline=elf.inspect(Path(baseproof['modules']['qdrv']['path']));candidate=elf.inspect(Path(closure['modules']['qdrv']['path']))
 require(candidate['parameters']==baseline['parameters'],'F344 parameter profile changed');require(candidate['functions']==baseline['functions'],'beacon preflight profile changed')
 require(closure['modules']['qdrv']['license']=='GPL' and not closure['modules']['qdrv']['proprietary_taint'],'qdrv license/taint conflict')
 require(set(closure['modules']['qdrv']['exports'])==set(baseproof['modules']['qdrv']['exports']),'wire/export surface changed')
 reuse_path=Path(closure['unchanged_peer_reuse']['manifest']);reuse=json.loads(reuse_path.read_text());require(sha(reuse_path)==closure['unchanged_peer_reuse']['sha256'],'reuse proof drift')
 for name,row in closure['modules'].items():
  require(sha(Path(row['path']))==row['sha256'],'artifact drift '+name)
  if name!='qdrv':require(row['sha256']==reuse['modules'][name]['sha256'],'peer binary changed '+name)
 config=(a.closure.parent/'kernel.config').read_text();require('# CONFIG_MODULE_FORCE_UNLOAD is not set' in config,'forced unload config unsupported')
 require(closure['kernel_config_sha256']==baseproof['kernel_config_sha256'],'F340 configuration changed')
 old={p.relative_to(BASE).as_posix():sha(p) for p in BASE.rglob('*') if p.is_file()};new={p.relative_to(SRC).as_posix():sha(p) for p in SRC.rglob('*') if p.is_file()}
 changed=sorted(k for k in set(old)|set(new) if old.get(k)!=new.get(k))
 expected={'qdrv/Makefile','qdrv/qdrv_control.c','qdrv/qdrv_module.c','qdrv/qdrv_soc.c','qdrv/qdrv_wlan.c','qdrv/qdrv_hostlink.c','qdrv/f355_lifetime.h','qdrv/qdrv_f355_lifetime.c','qdrv/qdrv_f355_lifetime.h'}
 require(set(changed)==expected,'unexpected F355 source delta')
 metadata_not_compiled=[]
 for name,digest in new.items():
  if name=='F338-source-binding.json':
   require(old.get(name)==digest,'inherited provenance metadata changed')
   metadata_not_compiled.append(name)
  else:require(pins.get('qdrv/'+name)==digest or name=='Makefile','live/built source drift '+name)
 out=Path('/workspace/OpenMitraStar-build/f355')/('f355-qualified-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 negative=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cc','-std=c11','-D_GNU_SOURCE','-DCONFIG_MODULE_FORCE_UNLOAD','-fsyntax-only','-pthread',linux(a.lifetime_test.parent/'test.c')],capture_output=True,text=True,timeout=30)
 (out/'forced-unload-rejection.txt').write_text(negative.stderr)
 require(negative.returncode!=0 and 'F355 requires CONFIG_MODULE_FORCE_UNLOAD disabled' in negative.stderr,'forced unload build guard did not reject')
 patch=[]
 for name in changed:
  oldtext=(BASE/name).read_text().splitlines(True) if (BASE/name).exists() else []
  newtext=(SRC/name).read_text().splitlines(True)
  patch.extend(difflib.unified_diff(oldtext,newtext,fromfile='F344/'+name,tofile='F355/'+name))
 (out/'final-source.diff').write_text(''.join(patch))
 module_dir=out/'modules';module_dir.mkdir()
 artifacts={}
 for name,row in closure['modules'].items():
  destination=module_dir/(name+'.ko');shutil.copyfile(row['path'],destination)
  require(sha(destination)==row['sha256'],'copy mismatch '+name)
  artifacts[name]={'path':str(destination),'bytes':destination.stat().st_size,'sha256':sha(destination)}
 (out/'load-order.txt').write_text('\n'.join(closure['load_order'])+'\n')
 shutil.copyfile(a.closure.parent/'a/qdrv/Module.symvers',out/'qdrv-Module.symvers')
 doc=ROOT/'docs/OPENMITRASTAR_F355_QDRV_LIFETIME.md';shutil.copyfile(doc,out/'README.md')
 after=shutil.disk_usage(ROOT).free;require(after>500*1024*1024,'C: completion free space guard')
 result={'schema':'openmitrastar.f355-qualified/v1','status':'PASS_OFFLINE_PINNED_LIFETIME_COHERENT_CLOSURE','module':artifacts['qdrv'],'modules':artifacts,'module_count':len(artifacts),'closure':{'path':str(a.closure),'sha256':sha(a.closure)},'tests':{'lifetime':{'path':str(a.lifetime_test),'sha256':sha(a.lifetime_test),'evidence':lt['stdout']},'proc_contract':{'path':str(a.proc_test),'sha256':sha(a.proc_test),'evidence':pt['stdout'],'contracts':len(pt['contracts'])},'forced_unload_negative':{'expected_rejection':True,'path':str(out/'forced-unload-rejection.txt'),'sha256':sha(out/'forced-unload-rejection.txt')}},'source_files_changed':changed,'source_hashes':new,'patch':{'path':str(out/'final-source.diff'),'sha256':sha(out/'final-source.diff')},'documentation':{'path':str(doc),'sha256':sha(doc)},'kernel_config_sha256':closure['kernel_config_sha256'],'kernel_module_c_sha256':lt['kernel_module_c_sha256'],'f344_unchanged':{'path':str(F344_MANIFEST),'sha256':sha(F344_MANIFEST)},'parameter_profile':candidate['parameters'],'imports_audited':len(closure['imports_audited']),'wire_abi_changed':False,'permanent_pin_release_supported':False,'pin_point':'before first matched policy-admitted control command except get/stop; before direct core reset','init_failure_before_commit_unpinned':True,'hardware_access':False,'module_loaded_on_target':False,'firmware_epoch_proven':False,'hot_restart_supported':False,'wifi_physical':'USER_DEFERRED','disk_guard':{'threshold_bytes':500*1024*1024,'c_free_before':before,'c_free_after':after,'bulk_output_drive':'D'}}
 result['inherited_metadata_not_compiled']=metadata_not_compiled
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'result':str(out/'result.json'),'sha256':sha(out/'result.json'),'status':result['status'],'module':artifacts['qdrv'],'module_count':len(artifacts),'imports_audited':result['imports_audited'],'changed_files':len(changed)},indent=2))
if __name__=='__main__':main()
