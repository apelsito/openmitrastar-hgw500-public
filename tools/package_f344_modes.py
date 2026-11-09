"""Seal the offline F344 component overlay; no installation or firmware write."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess,zipfile
import f334_qdrv_contract as elf
from f331_oem_postfilter_projection import linux
from f334_shadow_contract import SOURCE_DRIVER_CONTRACT
from f344_runtime_contract import native_start,driver_contract
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ('closure','native','abi','bootstrap','csa','gate','backend'):ap.add_argument('--'+n,type=Path,required=True)
 a=ap.parse_args();proofs={n:{'path':str(getattr(a,n)),'sha256':sha(getattr(a,n)),'result':json.loads(getattr(a,n).read_text())} for n in ('closure','native','abi','bootstrap','csa','gate','backend')}
 for n,p in proofs.items():require(p['result']['status'].startswith('PASS_'),'unqualified '+n)
 closure=proofs['closure']['result'];native=proofs['native']['result'];modules=closure['modules'];require(len(modules)==26 and 'qtn_radar_f338' in modules and 'qtn_radar_f341' not in modules,'wrong F344 closure')
 require(proofs['abi']['result']['closure_sha256']==sha(a.closure),'ABI witness is not this closure')
 require(proofs['backend']['result']['backend_sha256']==native['sources']['f344_backend.c'],'backend test/build differ')
 for name,digest in native['sources'].items():
  if name!='sha256-internal.c':require(sha(ROOT/'work/kernel-port/f344'/name)==digest,'native source drift '+name)
 candidate=elf.inspect(Path(modules['qdrv']['path']));baseline=elf.inspect(ROOT/'outputs/kernel-port/f338-qdrv-availability-20260921T132134Z/qdrv-a.ko')
 require(candidate['parameters']=={**baseline['parameters'],'openmitrastar_mode_workflow':0o400,'openmitrastar_mode_channel_hold':0o600},'qdrv parameter profile drift')
 require(candidate['functions']==baseline['functions'],'beacon preflight profile lost')
 require('wlan' in modules['qdrv']['dependencies'] and 'ieee80211_f344_policy_abi_v1' in modules['qdrv']['imports'],'host ABI marker dependency missing')
 wpa_path=ROOT/'outputs/userspace/f344-wpa-final-20260921T145403Z/manifest.json';wpa=json.loads(wpa_path.read_text());require(wpa['status']=='PASS_OFFLINE_BUILD_AND_NATIVE_CONTROL' and wpa['reproducible'],'WPA not qualified')
 f340=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f340-f321-watchdog-baseline-device-bound';fm=json.loads((f340/'manifest.json').read_text());rootfs=f340/fm['artifacts']['rootfs_squashfs']['file'];require(sha(rootfs)==fm['artifacts']['rootfs_squashfs']['sha256'],'F340 rootfs drift')
 require(closure['kernel_config_sha256']==fm['artifacts']['config']['sha256'],'F340/module ABI mismatch')
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','unsquashfs','-cat',linux(rootfs),'usr/share/openmitrastar/radio5g/driver-contract.env'],capture_output=True,timeout=25)
 require(not p.returncode and hashlib.sha256(p.stdout).hexdigest()==SOURCE_DRIVER_CONTRACT,'F340 original driver contract identity mismatch')
 out=ROOT/'outputs/handoff'/('f344-mode-components-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False);overlay=out/'overlay';entries={}
 def put(name,data,mode):
  path=overlay/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);entries[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'mode':mode}
 for name,row in modules.items():
  path=Path(row['path']);require(sha(path)==row['sha256'],'module drift '+name);put('lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/'+name+'.ko',path.read_bytes(),0o644)
 binaries={'om-f344-mode':native['artifact'],'wpa_supplicant-f344':wpa['artifacts']['wpa_supplicant'],'wpa_cli-f344':wpa['artifacts']['wpa_cli']}
 for name,row in binaries.items():
  path=Path(row['path']);require(sha(path)==row['sha256'],'binary drift '+name);put('usr/sbin/'+name,path.read_bytes(),0o755)
 loader=native_start((ROOT/'versions/lyoko-foundation-6.9.0-f315-radar-shadow/overlay/usr/sbin/om-radio5-start').read_bytes())
 require(hashlib.sha256(loader).hexdigest()==proofs['bootstrap']['result']['loader_sha256'],'bootstrap proof/build differ')
 put('usr/libexec/openmitrastar/om-radio5-start-f344',loader,0o755)
 put('usr/share/openmitrastar/radio5g/driver-contract.env',driver_contract(p.stdout,modules),0o644)
 put('etc/openmitrastar/features/qtn-f344-managed-modes-v1',b'OPENMITRASTAR_F344_MANAGED_MODES=0\n',0o644)
 put('usr/share/doc/openmitrastar/F344_MANAGED_MODES.md',(ROOT/'docs/OPENMITRASTAR_F344_MANAGED_MODES.md').read_bytes(),0o644)
 catalog=''.join(v['sha256']+'  /'+k+'\n' for k,v in sorted(entries.items())).encode();put('usr/share/openmitrastar/f344/artifacts.sha256',catalog,0o644)
 for lane in ('a','b'):
  with zipfile.ZipFile(out/('f344-components-'+lane+'.zip'),'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
   for name,row in sorted(entries.items()):
    info=zipfile.ZipInfo(name,(2026,9,21,0,0,0));info.create_system=3;info.external_attr=(0o100000|row['mode'])<<16;info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,(overlay/name).read_bytes())
 require(sha(out/'f344-components-a.zip')==sha(out/'f344-components-b.zip'),'component repack not reproducible')
 with zipfile.ZipFile(out/'f344-components-a.zip') as z:
  require(set(z.namelist())==set(entries),'unexpected/missing archive entries')
  for name,row in entries.items():require(hashlib.sha256(z.read(name)).hexdigest()==row['sha256'],'postpack hash mismatch '+name)
 result={'schema':'openmitrastar.f344-mode-components/v1','status':'PASS_OFFLINE_COMPONENTS_PARITY_INCOMPLETE_WIFI_DEFERRED','image_created':False,'installation_performed':False,'feature_default':False,'wifi_physical':'USER_DEFERRED','arc_userspace_execution':'UNRUN','muc_descriptor_reuse':'EOPNOTSUPP_UNTIL_PROVEN_NEW_FIRMWARE_EPOCH','boot_wiring':'VERSIONED_HELPER_ONLY_NOT_CONNECTED_TO_INIT','external_configuration_writers':'MUST_INVALIDATE_MANAGED_SNAPSHOT_BEFORE_MUTATION_NOT_INSTALLED','hardware_acquisition':False,'dfs_authority':False,'snapshot_incomplete_rejected':True,'rf_quiescence_claimed':False,'kernel_config_sha256':closure['kernel_config_sha256'],'proofs':{n:{k:v for k,v in row.items() if k!='result'} for n,row in proofs.items()},'wpa_proof':{'path':str(wpa_path),'sha256':sha(wpa_path)},'load_order':closure['load_order'],'imports_audited':len(closure['imports_audited']),'qdrv_parameters':candidate['parameters'],'artifacts':binaries,'qdrv':{k:modules['qdrv'][k] for k in ('path','bytes','sha256')},'provider':{k:modules['qtn_radar_f338'][k] for k in ('path','bytes','sha256')},'archive':{'path':str(out/'f344-components-a.zip'),'bytes':(out/'f344-components-a.zip').stat().st_size,'sha256':sha(out/'f344-components-a.zip'),'identical_repack':True},'catalog_entries':len(entries)-1,'postpack_verified':True,'files':entries}
 (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'manifest':str(out/'manifest.json'),'manifest_sha256':sha(out/'manifest.json'),'status':result['status'],'archive':result['archive'],'files':len(entries),'imports_audited':result['imports_audited']},indent=2))
if __name__=='__main__':main()
