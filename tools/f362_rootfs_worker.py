"""Integrate only the qualified F352 Ethernet module and helpers into F361."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
VERSION='lyoko-foundation-6.9.10-f362-dual-ethernet-device'
MODULE='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/ethernet/qtn-topaz-emac-f352.ko'
STORAGE_CATALOG='usr/share/openmitrastar/storage/artifacts.sha256'

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for name in ['source','overlay','module','helper','service','image','result']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--source-sha',required=True);p.add_argument('--build-id',required=True);p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 assert sha(a.source.read_bytes())==a.source_sha
 assert sha(a.module.read_bytes())=='41c5cb625b22776d0075207760df59fd20d4a34bddb1c7568adfa83391cbc05e'
 assert sha(a.helper.read_bytes())=='32e9727f253dfcca286d6038030343c5b9cb4146e5dc0dffc5afc8a8e3e8da15'
 assert sha(a.service.read_bytes())=='47abadab1543766715b6937d7263d7db351a152c35beb7d74d8fd3086d35f58b'
 with tempfile.TemporaryDirectory(prefix='f362-rootfs-',dir='/tmp') as directory:
  scratch=Path(directory);root=scratch/'root';verified=scratch/'verified';packed=scratch/'packed.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);old_catalog=(root/ARTIFACTS_PATH).read_bytes();verify_artifact_catalog(root,old_catalog)
  changes={MODULE:(a.module.read_bytes(),0o644),'usr/sbin/om-ethernet-f352':(a.helper.read_bytes(),0o755),'etc/init.d/S56-f352-ethernet':(a.service.read_bytes(),0o755)}
  for f in a.overlay.rglob('*'):
   assert not f.is_symlink()
   if f.is_file():changes[f.relative_to(a.overlay).as_posix()]=(f.read_bytes(),0o755)
  assert set(changes)=={MODULE,'usr/sbin/om-ethernet-f352','etc/init.d/S56-f352-ethernet','etc/init.d/S15-f352-driver'}
  assert all(name not in before for name in changes)
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
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
  services=sorted(f.name for f in (root/'etc/init.d').glob('S[0-9][0-9]-*'))
  assert services.index('S15-f352-driver')<services.index('S30-config')<services.index('S32-network')<services.index('S56-f352-ethernet')
  assert (root/'usr/sbin/ram-insmod-qtn').is_file()
  for name in ['etc/init.d/S15-f352-driver','etc/init.d/S56-f352-ethernet','usr/sbin/om-ethernet-f352']:
   subprocess.run(['sh','-n',str(root/name)],check=True)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);web.check_legacy_asset_metadata(verified);verify_artifact_catalog(verified)
  for line in (verified/STORAGE_CATALOG).read_text().splitlines():
   digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  protected=[name for name in before if name.startswith(('lib/modules/','usr/share/openmitrastar/device-identity/')) or name in ('usr/sbin/om-network-base','usr/sbin/om-radioctl','usr/sbin/om-radio5-start','usr/sbin/om-radio5-stop','usr/sbin/om-config-persist','usr/sbin/om-journal-ro','usr/sbin/om-watchdog-supervisor')]
  assert all(before[name]==after[name] for name in protected)
  shutil.copyfile(packed,a.image);a.result.write_text(json.dumps({'status':'PASS_F362_ROOTFS_DELTA','before':before,'after':after,'expected_changes':expected,'checks':checks,'changed_files':sorted(changes),'protected_entries_unchanged':len(protected),'existing_modules_unchanged':True,'radio_network_identity_unchanged':True,'startup_order':services,'startup_flash_writes':False,'automatic_watchdog_arm':False,'automatic_reboot':False},sort_keys=True)+'\n')
if __name__=='__main__':main()
