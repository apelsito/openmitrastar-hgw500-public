"""F365 cached DATA diagnostics only, preserving F364r3 startup/admission."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
VERSION='lyoko-foundation-6.9.13-f365-temperature-data-device'
SENSOR='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/temp_sens.ko'
HELPER='usr/sbin/om-temperature-f363'
PROFILE='usr/share/openmitrastar/temperature/profile.json'
CATALOG='usr/share/openmitrastar/temperature/artifacts.sha256'
STORAGE_CATALOG='usr/share/openmitrastar/storage/artifacts.sha256'
DIAGNOSTICS=b''' diagnostics)
  find_sensor
  # Both attributes return cached RAM only; never trigger a new sample.
  cat "$sensor/diag_hwmon" "$sensor/diag_legacy"
  ;;
'''

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('source','module','image','result'):p.add_argument('--'+name,type=Path,required=True)
 for name in ('source-sha','base-module-sha','module-sha','build-id'):p.add_argument('--'+name,required=True)
 p.add_argument('--epoch',type=int,required=True);a=p.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 assert sha(a.source.read_bytes())==a.source_sha and sha(a.module.read_bytes())==a.module_sha
 with tempfile.TemporaryDirectory(prefix='f365-rootfs-',dir='/tmp') as directory:
  scratch=Path(directory);root=scratch/'root';verified=scratch/'verified';packed=scratch/'packed.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);verify_artifact_catalog(root)
  assert before[SENSOR]['sha256']==a.base_module_sha
  changes={SENSOR:(a.module.read_bytes(),before[SENSOR]['mode'])}
  helper=(root/HELPER).read_bytes();assert helper.count(b' read)\n')==1 and b' diagnostics)\n' not in helper
  changed_helper=helper.replace(b' read)\n',DIAGNOSTICS+b' read)\n',1)
  assert changed_helper.count(b'load|status|enable|read')==1
  changed_helper=changed_helper.replace(b'load|status|enable|read',b'load|status|enable|read|diagnostics',1)
  assert changed_helper.replace(DIAGNOSTICS,b'',1).replace(b'load|status|enable|read|diagnostics',b'load|status|enable|read',1)==helper
  changes[HELPER]=(changed_helper,before[HELPER]['mode'])
  profile=json.loads((root/PROFILE).read_text())
  assert profile['default_enabled'] is False and profile['default_sensor_mmio'] is False
  profile.update(schema='openmitrastar.f365-temperature-data-profile/v1',diagnostic_revision=365,
                 diagnostic_command='om-temperature-f363 diagnostics',diagnostic_attributes=['diag_hwmon','diag_legacy'],
                 diagnostic_schema='openmitrastar.f365-temperature-access/v1',diagnostic_reads_cached_ram_only=True,
                 diagnostic_streams_separate=True,automatic_activation=False,
                 sensor_core_table_start_and_timeout_unchanged=True)
  changes[PROFILE]=((json.dumps(profile,sort_keys=True,indent=2)+'\n').encode(),before[PROFILE]['mode'])
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
  assert 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.9.12-f364r3-lifetime-device' in release
  release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if line.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if line.startswith('OPENMITRASTAR_BUILD_ID=') else line for line in release)+'\n'
  changes['etc/openmitrastar/release']=(release.encode(),0o644)
  for catalog in (CATALOG,ARTIFACTS_PATH,STORAGE_CATALOG):
   old=(root/catalog).read_bytes();rows=[]
   for line in old.decode().splitlines():
    digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
   new=('\n'.join(rows)+'\n').encode()
   if new!=old:changes[catalog]=(new,before[catalog]['mode'])
  expected={name:put(root,name,value,mode) for name,(value,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected)
  subprocess.run(['sh','-n',str(root/HELPER)],check=True)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);verify_artifact_catalog(verified)
  for catalog in (CATALOG,STORAGE_CATALOG):
   for line in (verified/catalog).read_text().splitlines():
    digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  unchanged=[name for name in before if name not in changes]
  assert all(before[name]==after[name] for name in unchanged)
  for name in ('etc/init.d/S16-f363-temperature','usr/sbin/om-radio5-start','usr/sbin/om-radio5-stop','etc/init.d/S90-ready'):
   assert before[name]==after[name]
  shutil.copyfile(packed,a.image)
  a.result.write_text(json.dumps({'status':'PASS_F365_ROOTFS_DIAGNOSTICS_DELTA','before':before,'after':after,
   'expected_changes':expected,'checks':checks,'changed_files':sorted(changes),'unchanged_entries':len(unchanged),
   'helper_existing_actions_and_module363_admission_unchanged':True,'provider_preload_and_radio_dirty_gate_unchanged':True,
   'automatic_sensor_activation':False,'diagnostic_reads_cached_ram_only':True,'radio_start_stop_unchanged':True,
   'qdrv_lifetime_ethernet_identity_journal_supervisor_unchanged':True,'hardware_actions':False},sort_keys=True)+'\n')
if __name__=='__main__':main()
