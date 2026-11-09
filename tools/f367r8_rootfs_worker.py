"""Replace only the reviewed R8 shell controller and release/catalog metadata."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
VERSION='lyoko-foundation-6.11.7-f367r8-mode-contract-device'
CONTROL='usr/sbin/om-f367-control'
PROFILE='usr/share/openmitrastar/dfs-f367/profile.json'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for name in ('source','control','image','result'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('source-sha','control-sha','build-id'):p.add_argument('--'+name,required=True)
 p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 assert sha(a.source.read_bytes())==a.source_sha and sha(a.control.read_bytes())==a.control_sha
 with tempfile.TemporaryDirectory(prefix='f367r8-rootfs-',dir='/tmp') as tmp:
  root=Path(tmp)/'root';verified=Path(tmp)/'verified';packed=Path(tmp)/'image.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);verify_artifact_catalog(root)
  assert '"$iwpriv" wifi0 mode 11ac20 ' in (root/CONTROL).read_text()
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
  assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.11.6-f367r7-clock-observation-device' in release
  release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if s.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if s.startswith('OPENMITRASTAR_BUILD_ID=') else s for s in release)+'\n'
  profile=json.loads((root/PROFILE).read_text());assert profile['runtime_revision']=='F367r7'
  profile.update(runtime_revision='F367r8',mode_setter_request='11ac',mode_getter_label='11ac20',channel_context_readback_deadline_ms=5000,one_write_per_mode_filter_channel=True,context_fault_before_success=True)
  changes={CONTROL:(a.control.read_bytes(),before[CONTROL]['mode']),'etc/openmitrastar/release':(release.encode(),before['etc/openmitrastar/release']['mode']),PROFILE:((json.dumps(profile,sort_keys=True,indent=2)+'\n').encode(),before[PROFILE]['mode'])}
  for catalog in ('usr/share/openmitrastar/temperature/artifacts.sha256','usr/share/openmitrastar/storage/artifacts.sha256',ARTIFACTS_PATH):
   original=(root/catalog).read_bytes();rows=[]
   for line in original.decode().splitlines():
    digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
   data=('\n'.join(rows)+'\n').encode()
   if data!=original:changes[catalog]=(data,before[catalog]['mode'])
  expected={name:put(root,name,data,mode) for name,(data,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected);verify_artifact_catalog(root)
  subprocess.run(['sh','-n',str(root/CONTROL)],check=True)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);verify_artifact_catalog(verified)
  assert all(before[name]==after[name] for name in before if name not in changes)
  for catalog in ('usr/share/openmitrastar/storage/artifacts.sha256','usr/share/openmitrastar/temperature/artifacts.sha256'):
   for line in (verified/catalog).read_text().splitlines():digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  assert set(changes)=={CONTROL,'etc/openmitrastar/release',PROFILE,ARTIFACTS_PATH,'usr/share/openmitrastar/storage/artifacts.sha256'}
  shutil.copyfile(packed,a.image)
  a.result.write_text(json.dumps(dict(status='PASS_F367R8_CONTROL_ONLY_ROOTFS',before=before,after=after,checks=checks,changed_files=sorted(changes),native_profile=profile,all_modules_and_native_binaries_unchanged=True,hardware_actions=False),sort_keys=True)+'\n')
if __name__=='__main__':main()
