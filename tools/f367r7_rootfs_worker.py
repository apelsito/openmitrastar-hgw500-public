"""R7 changes qdrv clock publication and its exact loader/catalog bindings."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
from f367r6_rootfs_worker import static_elf
VERSION='lyoko-foundation-6.11.6-f367r7-clock-observation-device'
QDRV='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'
NATIVE='usr/libexec/openmitrastar/om-radio5-start-f367-native'
CONTRACT='usr/share/openmitrastar/radio5g/driver-contract.env'
PROFILE='usr/share/openmitrastar/dfs-f367/profile.json'
HELPER='usr/sbin/om-f367-dfs-profile'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for name in ('source','qdrv','image','result'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('source-sha','qdrv-sha','build-id'):p.add_argument('--'+name,required=True)
 p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 assert sha(a.source.read_bytes())==a.source_sha and sha(a.qdrv.read_bytes())==a.qdrv_sha
 with tempfile.TemporaryDirectory(prefix='f367r7-rootfs-',dir='/tmp') as tmp:
  root=Path(tmp)/'root';verified=Path(tmp)/'verified';packed=Path(tmp)/'image.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);verify_artifact_catalog(root);static_elf((root/HELPER).read_bytes())
  previous=before[QDRV]['sha256'];assert previous=='ca441e1a435350a171a4bb48811d06332a194145dd5ed51edfb299542ac2b1b1'
  native=(root/NATIVE).read_bytes();assert previous.encode() in native
  native=native.replace(previous.encode(),a.qdrv_sha.encode())
  contract=(root/CONTRACT).read_text().splitlines();assert contract.count('QDRV_SHA256='+previous)==1
  contract='\n'.join('QDRV_SHA256='+a.qdrv_sha if s=='QDRV_SHA256='+previous else s for s in contract)+'\n'
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
  assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.11.5-f367r6-static-profile-device' in release
  release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if s.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if s.startswith('OPENMITRASTAR_BUILD_ID=') else s for s in release)+'\n'
  profile=json.loads((root/PROFILE).read_text());assert profile['runtime_revision']=='F367r6'
  profile.update(runtime_revision='F367r7',clock_publication='MAX_OF_RETAINED_NS_AND_TICK_DEADLINES',clock_admission_unchanged=True,clock_deadlines_unchanged=True)
  changes={QDRV:(a.qdrv.read_bytes(),before[QDRV]['mode']),NATIVE:(native,before[NATIVE]['mode']),CONTRACT:(contract.encode(),before[CONTRACT]['mode']),'etc/openmitrastar/release':(release.encode(),before['etc/openmitrastar/release']['mode']),PROFILE:((json.dumps(profile,sort_keys=True,indent=2)+'\n').encode(),before[PROFILE]['mode'])}
  for catalog in ('usr/share/openmitrastar/temperature/artifacts.sha256','usr/share/openmitrastar/storage/artifacts.sha256',ARTIFACTS_PATH):
   original=(root/catalog).read_bytes();rows=[]
   for line in original.decode().splitlines():
    digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
   data=('\n'.join(rows)+'\n').encode()
   if data!=original:changes[catalog]=(data,before[catalog]['mode'])
  expected={name:put(root,name,data,mode) for name,(data,mode) in changes.items()};web.validate_delta(before,web.inventory(root),expected);verify_artifact_catalog(root)
  subprocess.run(['sh','-n',str(root/NATIVE)],check=True)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);verify_artifact_catalog(verified)
  assert all(before[name]==after[name] for name in before if name not in changes)
  assert (verified/NATIVE).read_bytes()==(root/NATIVE).read_bytes()
  for catalog in ('usr/share/openmitrastar/storage/artifacts.sha256','usr/share/openmitrastar/temperature/artifacts.sha256'):
   for line in (verified/catalog).read_text().splitlines():digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  assert set(changes)=={QDRV,NATIVE,CONTRACT,'etc/openmitrastar/release',PROFILE,ARTIFACTS_PATH,'usr/share/openmitrastar/storage/artifacts.sha256'}
  stale=[name for name,row in after.items() if row['type']=='file' and previous.encode() in (verified/name).read_bytes()];assert not stale,stale
  shutil.copyfile(packed,a.image);a.result.write_text(json.dumps(dict(status='PASS_F367R7_CLOCK_ROOTFS',before=before,after=after,checks=checks,changed_files=sorted(changes),native_profile=profile,native_hash_pin_only=True,hardware_actions=False),sort_keys=True)+'\n')
if __name__=='__main__':main()
