"""R9 rootfs delta: traced qdrv/wlan/controller/status and exact bindings only."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH

VERSION='lyoko-foundation-6.11.8-f367r9-transition-observation-device'
MODULES='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/'
QDRV=MODULES+'qdrv.ko'
WLAN=MODULES+'wlan.ko'
NATIVE='usr/libexec/openmitrastar/om-radio5-start-f367-native'
CONTROL='usr/sbin/om-f367-control'
STATUS='usr/sbin/om-f367-status'
CONTRACT='usr/share/openmitrastar/radio5g/driver-contract.env'
PROFILE='usr/share/openmitrastar/dfs-f367/profile.json'
RELEASE='etc/openmitrastar/release'
STORAGE='usr/share/openmitrastar/storage/artifacts.sha256'

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
 p=argparse.ArgumentParser()
 for name in ('source','qdrv','wlan','control','status','image','result'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('source-sha','qdrv-sha','wlan-sha','control-sha','status-sha','build-id'):p.add_argument('--'+name,required=True)
 p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 for name in ('source','qdrv','wlan','control','status'):assert sha(getattr(a,name).read_bytes())==getattr(a,name+'_sha')
 with tempfile.TemporaryDirectory(prefix='f367r9-rootfs-',dir='/tmp') as tmp:
  root=Path(tmp)/'root';verified=Path(tmp)/'verified';packed=Path(tmp)/'image.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);verify_artifact_catalog(root)
  native_original=(root/NATIVE).read_bytes();native=native_original
  contract_original=(root/CONTRACT).read_bytes();contract=contract_original
  assert before[QDRV]['sha256'].encode() in native and before[QDRV]['sha256'].encode() in contract
  for name,digest in ((QDRV,a.qdrv_sha),(WLAN,a.wlan_sha)):
   native=native.replace(before[name]['sha256'].encode(),digest.encode())
   contract=contract.replace(before[name]['sha256'].encode(),digest.encode())
  reverted=native.replace(a.qdrv_sha.encode(),before[QDRV]['sha256'].encode()).replace(a.wlan_sha.encode(),before[WLAN]['sha256'].encode())
  assert reverted==native_original
  release=(root/RELEASE).read_text().splitlines()
  assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.11.7-f367r8-mode-contract-device' in release
  release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if s.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if s.startswith('OPENMITRASTAR_BUILD_ID=') else s for s in release)+'\n'
  profile=json.loads((root/PROFILE).read_text());assert profile['runtime_revision']=='F367r8'
  profile.update(runtime_revision='F367r9',transition_observation_only=True,trace_first_target_channel=52,trace_window_ms=8000,trace_hostlink_commands=[38,17,35,26],trace_hostlink_line_budget=48,trace_progress_interval_ms=1000,trace_peer_csa_once=True,trace_status_requires_env=True,functional_deadlines_unchanged=True)
  replacements={QDRV:a.qdrv.read_bytes(),WLAN:a.wlan.read_bytes(),CONTROL:a.control.read_bytes(),STATUS:a.status.read_bytes(),NATIVE:native,CONTRACT:contract,RELEASE:release.encode(),PROFILE:(json.dumps(profile,sort_keys=True,indent=2)+'\n').encode()}
  changes={name:(data,before[name]['mode']) for name,data in replacements.items() if data!=(root/name).read_bytes()}
  for catalog in ('usr/share/openmitrastar/temperature/artifacts.sha256',STORAGE,ARTIFACTS_PATH):
   original=(root/catalog).read_bytes();rows=[]
   for line in original.decode().splitlines():
    digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
   data=('\n'.join(rows)+'\n').encode()
   if data!=original:changes[catalog]=(data,before[catalog]['mode'])
  expected={name:put(root,name,data,mode) for name,(data,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected);verify_artifact_catalog(root)
  for name in (NATIVE,CONTROL,STATUS):subprocess.run(['sh','-n',str(root/name)],check=True)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);verify_artifact_catalog(verified)
  assert all(before[name]==after[name] for name in before if name not in changes)
  for catalog in (STORAGE,'usr/share/openmitrastar/temperature/artifacts.sha256'):
   for line in (verified/catalog).read_text().splitlines():digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  assert set(changes)=={QDRV,WLAN,NATIVE,CONTROL,STATUS,CONTRACT,RELEASE,PROFILE,ARTIFACTS_PATH,STORAGE}
  shutil.copyfile(packed,a.image)
  a.result.write_text(json.dumps(dict(status='PASS_F367R9_OBSERVATION_ROOTFS',before=before,after=after,checks=checks,changed_files=sorted(changes),native_profile=profile,native_hash_pins_only=True,all_other_entries_unchanged=True,hardware_actions=False),sort_keys=True)+'\n')
if __name__=='__main__':main()
