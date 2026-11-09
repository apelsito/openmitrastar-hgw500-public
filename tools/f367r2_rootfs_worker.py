"""Repack exact F365 with bounded native DFS diagnostics; no hardware."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
from f367r2_runtime_contract import VERSION,overlay,native_start
MODULE='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/'
CONTRACT='usr/share/openmitrastar/radio5g/driver-contract.env'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('source','qdrv','provider','engine','supervisor','image','result'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('source-sha','qdrv-sha','provider-sha','engine-sha','supervisor-sha','build-id'):p.add_argument('--'+name,required=True)
 p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 for name in ('source','qdrv','provider','engine','supervisor'):assert sha(getattr(a,name).read_bytes())==getattr(a,name+'_sha')
 with tempfile.TemporaryDirectory(prefix='f367-rootfs-',dir='/tmp') as directory:
  scratch=Path(directory);root=scratch/'root';verified=scratch/'verified';packed=scratch/'packed.squashfs'
  subprocess.run(['unsquashfs','-processors','1','no-progress' if False else '-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);verify_artifact_catalog(root)
  contents=overlay();changes={name:(data,0o755) for name,data in contents.items()}
  old_qdrv=before[MODULE+'qdrv.ko']['sha256'];start=(root/'usr/sbin/om-radio5-start').read_bytes()
  native=native_start(start,old_qdrv,a.qdrv_sha)
  changes['usr/libexec/openmitrastar/om-radio5-start-f367-native']=(native,0o755)
  changes[MODULE+'qdrv.ko']=(a.qdrv.read_bytes(),0o644)
  changes[MODULE+'qtn_radar_f367.ko']=(a.provider.read_bytes(),0o644)
  changes['usr/sbin/om-radar-engine-f367']=(a.engine.read_bytes(),0o755)
  changes['usr/sbin/om-watchdog-supervisor-f367']=(a.supervisor.read_bytes(),0o755)
  contract=(root/CONTRACT).read_text().splitlines();assert sum(x.startswith('QDRV_SHA256=') for x in contract)==1
  changes[CONTRACT]=(('\n'.join('QDRV_SHA256='+a.qdrv_sha if x.startswith('QDRV_SHA256=') else x for x in contract)+'\nRADAR_F367_SHA256='+a.provider_sha+'\n').encode(),0o644)
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
  assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.9.13-f365-temperature-data-device' in release
  release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if x.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if x.startswith('OPENMITRASTAR_BUILD_ID=') else x for x in release)+'\n'
  changes['etc/openmitrastar/release']=(release.encode(),0o644)
  profile={'schema':'openmitrastar.f367-ap-dfs-profile/v1','native_provider':'qtn_radar_f367','provider_telemetry_abi':'openmitrastar.f341-provider/v1','userspace_wire_abi':'F338','device':'/dev/om-radar-f338','provider_license':'GPL','oem_math_location':'separate userspace process','engine_sha256':a.engine_sha,'callback_authority':1,'release_qualified':0,'bootstrap_channel':36,'bootstrap_bandwidth':80,'dfs_channel':52,'dfs_bandwidth':20,'escape_channel':36,'quarantine_ms':1800000,'quarantine_policy':'local conservative policy because NOP is not persisted','cac_ms':70000,'nop_ms':1800000,'watchdog_session_ms':5400000,'health_lease_ms':5000,'five_ghz_boot_pending':True,'automatic_acquisition':False,'automatic_watchdog_arm':False,'physical_acceptance':'CAC_NOP_CLIENT_UNRUN','dirty_unload_supported':False,'software_injection_is_rf_detection':False,'kernel_state':'/sys/module/qdrv/parameters/openmitrastar_dfs_state','kernel_control':'/sys/module/qdrv/parameters/openmitrastar_dfs_control','controller':'om-f367-control','supervisor_path':'/usr/sbin/om-watchdog-supervisor-f367','supervisor_sha256':a.supervisor_sha}
  profile.update(runtime_revision='F367r2',preamble_phase_ms=30000,module_load_phase_ms=30000,keeper_ack_required_before_module_load=True,foreground_preamble_health=True)
  changes['usr/share/openmitrastar/dfs-f367/profile.json']=((json.dumps(profile,sort_keys=True,indent=2)+'\n').encode(),0o644)
  # All helpers and native binaries are covered by the existing full radio
  # catalogue. Other catalogues retain their original membership and receive
  # only hashes changed by this declared delta.
  for catalog in ('usr/share/openmitrastar/temperature/artifacts.sha256','usr/share/openmitrastar/storage/artifacts.sha256'):
   original=(root/catalog).read_bytes();rows=[]
   for line in original.decode().splitlines():
    digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
   changed=('\n'.join(rows)+'\n').encode()
   if changed!=original:changes[catalog]=(changed,before[catalog]['mode'])
  rows={line.split('  ',1)[1].lstrip('/'):line.split('  ',1)[0] for line in (root/ARTIFACTS_PATH).read_text().splitlines()}
  for name,(data,mode) in changes.items():rows[name]=sha(data)
  changes[ARTIFACTS_PATH]=(''.join(digest+'  /'+name+'\n' for name,digest in sorted(rows.items())).encode(),0o644)
  expected={name:put(root,name,data,mode) for name,(data,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected);verify_artifact_catalog(root)
  for name in contents:subprocess.run(['sh','-n',str(root/name)],check=True)
  subprocess.run(['sh','-n',str(root/'usr/libexec/openmitrastar/om-radio5-start-f367-native')],check=True)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);verify_artifact_catalog(verified)
  for catalog in ('usr/share/openmitrastar/temperature/artifacts.sha256','usr/share/openmitrastar/storage/artifacts.sha256'):
   for line in (verified/catalog).read_text().splitlines():digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  protected=[name for name in before if name not in changes];assert all(before[name]==after[name] for name in protected)
  preserved=['etc/init.d/S15-f352-driver','etc/init.d/S16-f363-temperature','etc/init.d/S55-radio5-ap','etc/init.d/S56-f352-ethernet','etc/init.d/S90-ready','usr/sbin/om-watchdog-supervisor','usr/sbin/om-temperature-f363',MODULE+'temp_sens.ko']
  assert all(before[name]==after[name] for name in preserved)
  # F365 admission of the preloaded sensor and management-path source remain
  # exact substrings, while no normal init or UI entrypoint arms acquisition.
  assert '/usr/sbin/om-temperature-f363 require-module || refuse f363-preloaded-temperature-module' in native.decode()
  assert all('om-f367-control' not in (verified/name).read_text(errors='ignore') for name in after if name.startswith('etc/init.d/') and after[name]['type']=='file')
  stale=[name for name,row in after.items() if row['type']=='file' and old_qdrv.encode() in (verified/name).read_bytes()]
  assert not stale,stale
  qdrv_bindings=[name for name,row in after.items() if row['type']=='file' and a.qdrv_sha.encode() in (verified/name).read_bytes()]
  assert set(qdrv_bindings)=={CONTRACT,ARTIFACTS_PATH,'usr/libexec/openmitrastar/om-radio5-start-f367-native'},qdrv_bindings
  shutil.copyfile(packed,a.image)
  a.result.write_text(json.dumps({'status':'PASS_F367_NATIVE_START_ROOTFS','before':before,'after':after,'checks':checks,'changed_files':sorted(changes),'unchanged_entries':len(protected),'preserved_files':preserved,'runtime_bindings':{'/'+name:after[name]['sha256'] for name in changes if after[name]['type']=='file'},'native_donor_sha256':sha(start),'native_sha256':sha(native),'native_profile':profile,'hardware_actions':False},sort_keys=True)+'\n')
if __name__=='__main__':main()
