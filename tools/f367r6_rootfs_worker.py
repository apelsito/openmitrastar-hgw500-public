"""Replace only the helper link and metadata in the exact R5 rootfs."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,struct,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
VERSION='lyoko-foundation-6.11.5-f367r6-static-profile-device'
HELPER='usr/sbin/om-f367-dfs-profile'
PROFILE='usr/share/openmitrastar/dfs-f367/profile.json'
def sha(data):return hashlib.sha256(data).hexdigest()
def static_elf(data):
 assert data[:6]==b'\x7fELF\x01\x01'
 assert struct.unpack_from('<H',data,18)[0]==93
 assert struct.unpack_from('<I',data,36)[0]==0x403
 offset=struct.unpack_from('<I',data,28)[0];size,count=struct.unpack_from('<HH',data,42)
 assert size==32 and count>0
 assert all(struct.unpack_from('<I',data,offset+i*size)[0] not in (2,3) for i in range(count))
def main():
 p=argparse.ArgumentParser()
 for name in ('source','helper','image','result'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('source-sha','helper-sha','build-id'):p.add_argument('--'+name,required=True)
 p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 assert sha(a.source.read_bytes())==a.source_sha and sha(a.helper.read_bytes())==a.helper_sha
 static_elf(a.helper.read_bytes())
 with tempfile.TemporaryDirectory(prefix='f367r6-rootfs-',dir='/tmp') as tmp:
  root=Path(tmp)/'root';verified=Path(tmp)/'verified';packed=Path(tmp)/'image.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);verify_artifact_catalog(root)
  assert before[HELPER]['sha256']=='7e028d6383a6a7a3aab08dc5c09eada34a1fb269deb3ee6b8be33f226097ee69'
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
  assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.11.4-f367r5-regulatory-profile-device' in release
  release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if s.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if s.startswith('OPENMITRASTAR_BUILD_ID=') else s for s in release)+'\n'
  profile=json.loads((root/PROFILE).read_text());assert profile['runtime_revision']=='F367r5'
  profile.update(runtime_revision='F367r6',profile_helper_sha256=a.helper_sha,profile_helper_static=True,profile_helper_pt_interp=False,profile_helper_dt_needed=[],profile_helper_noatomic=True)
  changes={HELPER:(a.helper.read_bytes(),before[HELPER]['mode']),'etc/openmitrastar/release':(release.encode(),before['etc/openmitrastar/release']['mode']),PROFILE:((json.dumps(profile,sort_keys=True,indent=2)+'\n').encode(),before[PROFILE]['mode'])}
  for catalog in ('usr/share/openmitrastar/temperature/artifacts.sha256','usr/share/openmitrastar/storage/artifacts.sha256',ARTIFACTS_PATH):
   original=(root/catalog).read_bytes();rows=[]
   for line in original.decode().splitlines():
    digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
   data=('\n'.join(rows)+'\n').encode()
   if data!=original:changes[catalog]=(data,before[catalog]['mode'])
  expected={name:put(root,name,data,mode) for name,(data,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected);verify_artifact_catalog(root)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);verify_artifact_catalog(verified);static_elf((verified/HELPER).read_bytes())
  assert all(before[name]==after[name] for name in before if name not in changes)
  for catalog in ('usr/share/openmitrastar/storage/artifacts.sha256','usr/share/openmitrastar/temperature/artifacts.sha256'):
   for line in (verified/catalog).read_text().splitlines():digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  assert set(changes)=={HELPER,'etc/openmitrastar/release',PROFILE,ARTIFACTS_PATH,'usr/share/openmitrastar/storage/artifacts.sha256'}
  shutil.copyfile(packed,a.image)
  a.result.write_text(json.dumps(dict(status='PASS_F367R6_STATIC_ONLY_ROOTFS',before=before,after=after,checks=checks,changed_files=sorted(changes),native_profile=profile,static_elf_verified=True,hardware_actions=False),sort_keys=True)+'\n')
if __name__=='__main__':main()
