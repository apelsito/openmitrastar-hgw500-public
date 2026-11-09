"""Apply the F361 userspace overlay to F358. Kernel/DT/supervisor unchanged."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
VERSION='lyoko-foundation-6.9.9-f361-config-persistence-device'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for name in ['source','overlay','reader','image','result']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--source-sha',required=True);p.add_argument('--reader-sha',required=True);p.add_argument('--build-id',required=True);p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 assert sha(a.source.read_bytes())==a.source_sha and sha(a.reader.read_bytes())==a.reader_sha
 with tempfile.TemporaryDirectory(prefix='f361-rootfs-',dir='/tmp') as directory:
  scratch=Path(directory);root=scratch/'root';verified=scratch/'verified';packed=scratch/'packed.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);old_catalog=(root/ARTIFACTS_PATH).read_bytes();verify_artifact_catalog(root,old_catalog)
  changes={}
  for f in a.overlay.rglob('*'):
   if f.is_symlink():raise ValueError('overlay symlink')
   if f.is_file():
    name=f.relative_to(a.overlay).as_posix();changes[name]=(f.read_bytes(),0o644 if name.startswith('etc/openmitrastar/features/') else 0o755)
  changes['usr/sbin/om-journal-ro']=(a.reader.read_bytes(),0o755)
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
  release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if s.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if s.startswith('OPENMITRASTAR_BUILD_ID=') else s for s in release)+'\n'
  changes['etc/openmitrastar/release']=(release.encode(),0o644)
  profile=json.loads((root/'usr/share/openmitrastar/storage/profile.json').read_text())
  profile.update(schema='openmitrastar.f361-config-persistence-profile/v1',autoload=True,boot_load_parameters='allow_hw=1 allow_program=1',startup_mmio=False,automatic_writes=False,boot_consumer='MTD-ROM-snapshot/F342',managed_settings=22,derived_fields_ignored=['ORIGIN_MTD5_IMPORTED','RADIO5G_SSID','RADIO5G_CONFIG_SOURCE'],normal_save_api='config/store action=commit',radio_transaction_commit='volatile',automatic_watchdog_arm=False,automatic_reboot=False,bus_fault_automatic_recovery=False,rollback_supported=False)
  changes['usr/share/openmitrastar/storage/profile.json']=((json.dumps(profile,sort_keys=True,indent=2)+'\n').encode(),0o644)
  rows=[]
  for line in old_catalog.decode().splitlines():
   old_digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else old_digest)+'  '+path)
  new_catalog=('\n'.join(rows)+'\n').encode()
  if new_catalog!=old_catalog:changes[ARTIFACTS_PATH]=(new_catalog,0o644)
  existing=(root/'usr/share/openmitrastar/storage/artifacts.sha256').read_text().splitlines();entries={row.split('  ',1)[1].lstrip('/'):row.split('  ',1)[0] for row in existing}
  entries.update({name:sha(value[0]) for name,value in changes.items() if name!=ARTIFACTS_PATH})
  changes['usr/share/openmitrastar/storage/artifacts.sha256']=((''.join(value+'  /'+name+'\n' for name,value in sorted(entries.items()))).encode(),0o644)
  expected={name:put(root,name,value,mode) for name,(value,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);web.check_legacy_asset_metadata(verified);verify_artifact_catalog(verified,new_catalog)
  protected=[name for name in before if name.startswith(('lib/modules/','usr/share/openmitrastar/device-identity/')) or name in ('usr/sbin/om-radioctl','usr/sbin/om-radio5-start','usr/sbin/om-radio5-stop','usr/sbin/om-qtnctl','usr/sbin/om-rtlctl','usr/sbin/om-config-transaction','usr/sbin/om-config-prepare','usr/sbin/om-watchdog-supervisor')]
  assert all(before[name]==after[name] for name in protected)
  shutil.copyfile(packed,a.image);a.result.write_text(json.dumps({'status':'PASS_F361_ROOTFS_DELTA','before':before,'after':after,'expected_changes':expected,'checks':checks,'changed_files':sorted(changes),'protected_entries_unchanged':len(protected),'kernel_or_radio_changes':False,'startup_controller_commands':False,'startup_writes':False,'automatic_watchdog_arm':False,'automatic_reboot':False},sort_keys=True)+'\n')
if __name__=='__main__':main()
