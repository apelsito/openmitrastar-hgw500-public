"""Replace only qdrv and its metadata in the real F363 SquashFS image."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
VERSION='lyoko-foundation-6.9.12-f364-lifetime-device'
QDRV='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko'
CONTRACT='usr/share/openmitrastar/radio5g/driver-contract.env'
STORAGE_CATALOG='usr/share/openmitrastar/storage/artifacts.sha256'

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in ('source','module','image','result'):p.add_argument('--'+n,type=Path,required=True)
 for n in ('source-sha','base-qdrv-sha','module-sha','build-id'):p.add_argument('--'+n,required=True)
 p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 assert sha(a.source.read_bytes())==a.source_sha and sha(a.module.read_bytes())==a.module_sha
 with tempfile.TemporaryDirectory(prefix='f364-rootfs-',dir='/tmp') as directory:
  scratch=Path(directory);root=scratch/'root';verified=scratch/'verified';packed=scratch/'packed.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);old_catalog=(root/ARTIFACTS_PATH).read_bytes();verify_artifact_catalog(root,old_catalog)
  assert before[QDRV]['sha256']==a.base_qdrv_sha
  changes={QDRV:(a.module.read_bytes(),before[QDRV]['mode'])}
  contract=(root/CONTRACT).read_text().splitlines();assert sum(s.startswith('QDRV_SHA256=') for s in contract)==1
  changes[CONTRACT]=(('\n'.join('QDRV_SHA256='+a.module_sha if s.startswith('QDRV_SHA256=') else s for s in contract)+'\n').encode(),0o644)
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
  assert any('f363' in s and s.startswith('OPENMITRASTAR_PRODUCT_VERSION=') for s in release)
  release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if s.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if s.startswith('OPENMITRASTAR_BUILD_ID=') else s for s in release)+'\n'
  changes['etc/openmitrastar/release']=(release.encode(),0o644)
  for catalog in [ARTIFACTS_PATH,STORAGE_CATALOG]:
   old=(root/catalog).read_bytes();rows=[]
   for line in old.decode().splitlines():
    digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
   new=('\n'.join(rows)+'\n').encode()
   if new!=old:changes[catalog]=(new,0o644)
  expected={name:put(root,name,value,mode) for name,(value,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);verify_artifact_catalog(verified)
  for line in (verified/STORAGE_CATALOG).read_text().splitlines():
   digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  protected=[name for name in before if name not in changes]
  assert all(before[name]==after[name] for name in protected)
  shutil.copyfile(packed,a.image)
  a.result.write_text(json.dumps({'status':'PASS_F364_ROOTFS_DELTA','before':before,'after':after,
   'expected_changes':expected,'checks':checks,'changed_files':sorted(changes),'unchanged_entries':len(protected),
   'f363_thermal_sensor_and_helpers_preserved':True,'ethernet_and_identity_preserved':True,
   'radio_start_stop_helpers_unchanged':True,'lifetime_adapter':'F355 permanent ownership',
   'new_radio_modes_enabled':False,'automatic_arm':False,'automatic_reboot':False,'hardware_actions':False},sort_keys=True)+'\n')
if __name__=='__main__':main()
