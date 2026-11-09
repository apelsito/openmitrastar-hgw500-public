"""Add only F363 temperature components to the immutable F362 rootfs."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
VERSION='lyoko-foundation-6.9.11-f363-temperature-diagnostic-device'
MODULES='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g'
STORAGE_CATALOG='usr/share/openmitrastar/storage/artifacts.sha256'
TEMP_CATALOG='usr/share/openmitrastar/temperature/artifacts.sha256'
OLD_QDRV='0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 ap=argparse.ArgumentParser()
 for n in ('source','overlay','hwmon','sensor','qdrv','image','result'):ap.add_argument('--'+n,type=Path,required=True)
 ap.add_argument('--source-sha',required=True);ap.add_argument('--build-id',required=True);ap.add_argument('--epoch',required=True,type=int);a=ap.parse_args()
 assert os.name=='posix' and os.geteuid()==0 and not a.image.exists() and not a.result.exists()
 assert sha(a.source.read_bytes())==a.source_sha
 with tempfile.TemporaryDirectory(prefix='f363-rootfs-',dir='/tmp') as directory:
  scratch=Path(directory);root=scratch/'root';verified=scratch/'verified';packed=scratch/'packed.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);verify_artifact_catalog(root)
  assert sha((root/MODULES/'qdrv.ko').read_bytes())==OLD_QDRV
  changes={MODULES+'/hwmon.ko':(a.hwmon.read_bytes(),0o644),MODULES+'/temp_sens.ko':(a.sensor.read_bytes(),0o644),MODULES+'/qdrv.ko':(a.qdrv.read_bytes(),0o644)}
  for f in a.overlay.rglob('*'):
   assert not f.is_symlink()
   if f.is_file():changes[f.relative_to(a.overlay).as_posix()]=(f.read_bytes(),0o755)
  assert set(changes)=={MODULES+'/'+n for n in ('hwmon.ko','temp_sens.ko','qdrv.ko')}|{'usr/sbin/om-temperature-f363','etc/init.d/S16-f363-temperature'}
  start=(root/'usr/sbin/om-radio5-start').read_bytes();assert sha(start)=='02df465d171abc459531f861f0833466b3a4d56a18cb078c735bb42fe1b0f35c'
  assert start.count(b'load_module temp_sens.ko')==1 and start.count(OLD_QDRV.encode())==1
  start=start.replace(b'load_module temp_sens.ko',b'/usr/sbin/om-temperature-f363 require-module || refuse f363-temperature-module').replace(OLD_QDRV.encode(),sha(a.qdrv.read_bytes()).encode())
  changes['usr/sbin/om-radio5-start']=(start,0o755)
  contract=(root/'usr/share/openmitrastar/radio5g/driver-contract.env').read_text();lines=contract.splitlines();assert sum(line.startswith('QDRV_SHA256=') for line in lines)==1
  contract='\n'.join('QDRV_SHA256='+sha(a.qdrv.read_bytes()) if line.startswith('QDRV_SHA256=') else line for line in lines)+'\n'
  changes['usr/share/openmitrastar/radio5g/driver-contract.env']=(contract.encode(),0o644)
  release=(root/'etc/openmitrastar/release').read_text().splitlines();release='\n'.join('OPENMITRASTAR_PRODUCT_VERSION='+VERSION if s.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if s.startswith('OPENMITRASTAR_BUILD_ID=') else s for s in release)+'\n'
  changes['etc/openmitrastar/release']=(release.encode(),0o644)
  profile={'schema':'openmitrastar.f363-temperature/v1','hwmon_name':'topaz_internal','legacy_module_replaced':True,'default_sensor_mmio':False,'default_enabled':False,'enable_operation':'om-temperature-f363 enable','read_operation':'om-temperature-f363 read','enable_is_one_shot_per_driver_instance':True,'clock_frequency_known':False,'physical_sensor_qualified':False,'conversion':'F339 OEM 34-entry curve; 5C interval upper bound','default_error':-19,'shutdown_protocol_added':False}
  changes['usr/share/openmitrastar/temperature/profile.json']=((json.dumps(profile,sort_keys=True,indent=2)+'\n').encode(),0o644)
  tracked=[MODULES+'/hwmon.ko',MODULES+'/temp_sens.ko','usr/sbin/om-temperature-f363','etc/init.d/S16-f363-temperature','usr/share/openmitrastar/temperature/profile.json']
  changes[TEMP_CATALOG]=((''.join(sha(changes[n][0])+'  /'+n+'\n' for n in sorted(tracked))).encode(),0o644)
  for catalog in (ARTIFACTS_PATH,STORAGE_CATALOG):
   old=(root/catalog).read_bytes();rows=[]
   for line in old.decode().splitlines():
    digest,path=line.split('  ',1);name=path.lstrip('/');rows.append((sha(changes[name][0]) if name in changes else digest)+'  '+path)
   new=('\n'.join(rows)+'\n').encode()
   if new!=old:changes[catalog]=(new,0o644)
  expected={name:put(root,name,data,mode) for name,(data,mode) in changes.items()};web.validate_delta(before,web.inventory(root),expected)
  order=sorted(f.name for f in (root/'etc/init.d').glob('S[0-9][0-9]-*'))
  assert order.index('S15-f352-driver')<order.index('S16-f363-temperature')<order.index('S30-config')
  for path in ('usr/sbin/om-temperature-f363','etc/init.d/S16-f363-temperature','usr/sbin/om-radio5-start'):subprocess.run(['sh','-n',str(root/path)],check=True)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);verify_artifact_catalog(verified);web.check_legacy_asset_metadata(verified)
  for catalog in (STORAGE_CATALOG,TEMP_CATALOG):
   for line in (verified/catalog).read_text().splitlines():
    digest,path=line.split('  ',1);assert sha((verified/path.lstrip('/')).read_bytes())==digest
  for name in before:
   if name not in changes:assert before[name]==after[name]
  assert before['usr/sbin/om-watchdog-supervisor']==after['usr/sbin/om-watchdog-supervisor']
  shutil.copyfile(packed,a.image);a.result.write_text(json.dumps({'status':'PASS_F363_ROOTFS_DELTA','before':before,'after':after,'changed_files':sorted(changes),'expected_changes':expected,'checks':checks,'startup_order':order,'default_sensor_mmio':False,'startup_flash_writes':False,'automatic_arm':False,'automatic_reboot':False},sort_keys=True)+'\n')
if __name__=='__main__':main()
