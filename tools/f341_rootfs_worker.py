"""Repack F341 from an exact F340 baseline; no hardware or activation."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,tempfile
import f334_shadow_contract as catalog
import f341_runtime_contract as contract
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
MODULE_DIR=catalog.MODULE_DIR
RELEASE=catalog.RELEASE_PATH
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for name in ('source','source-manifest','overlay','module-dir','closure-manifest','engine','donor-start','image','result'):ap.add_argument('--'+name,type=Path,required=True)
 ap.add_argument('--source-sha256',required=True);ap.add_argument('--build-id',required=True);ap.add_argument('--epoch',required=True,type=int)
 a=ap.parse_args()
 if os.name!='posix' or os.geteuid()!=0:raise ValueError('F341 repack requires isolated Linux build environment')
 if a.image.exists() or a.result.exists():raise ValueError('immutable F341 outputs already exist')
 if web.sha256(a.source)!=a.source_sha256:raise ValueError('F340 rootfs identity mismatch')
 source_manifest=json.loads(a.source_manifest.read_text());closure=json.loads(a.closure_manifest.read_text())
 if not closure['status'].startswith('PASS_'):raise ValueError('F341 closure is not offline qualified')
 if closure['kernel_config_sha256']!=source_manifest['artifacts']['config']['sha256']:raise ValueError('F340 rootfs image and F341 module config mismatch')
 rows=closure['modules'];hashes={name:row['sha256'] for name,row in rows.items()}
 if len(rows)!=26 or 'qtn_radar_f341' not in rows or 'qtn_radar_f338' in rows:raise ValueError('F341 closure identity/count mismatch')
 if web.sha256(a.engine)!=closure['engine']['sha256']:raise ValueError('exact ARC engine mismatch')
 helpers={}
 for p in a.overlay.rglob('*'):
  if p.is_symlink():raise ValueError('symlink in F341 helper overlay')
  if p.is_file():helpers[p.relative_to(a.overlay).as_posix()]=p.read_bytes()
 required={'usr/sbin/'+n for n in ('om-f341-stage','om-f341-diagnostic','om-f341-status','om-radio5-start','om-radio5-stop','om-radarctl')}
 if set(helpers)!=required:raise ValueError('F341 overlay must contain exact reviewed helpers')
 with tempfile.TemporaryDirectory(prefix='f341-rootfs-',dir='/tmp') as directory:
  scratch=Path(directory);root=scratch/'root';packed=scratch/'packed.squashfs';verified=scratch/'verified'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);old_catalog=(root/catalog.ARTIFACTS_PATH).read_bytes();source_catalog=catalog.verify_artifact_catalog(root,old_catalog)
  release=(root/RELEASE).read_text().splitlines();release='\n'.join((line.split('=',1)[0]+'='+contract.PRODUCT_VERSION if line.startswith('OPENMITRASTAR_PRODUCT_VERSION=') else 'OPENMITRASTAR_BUILD_ID='+a.build_id if line.startswith('OPENMITRASTAR_BUILD_ID=') else line) for line in release)+'\n'
  changes={path:(data,0o755) for path,data in helpers.items()}
  changes[RELEASE]=(release.encode('ascii'),0o644)
  changes[catalog.API_PATH]=(catalog.api_bytes((root/catalog.API_PATH).read_bytes()),0o755)
  changes['usr/libexec/openmitrastar/om-radio5-start-f341-native']=(contract.native_start(a.donor_start.read_bytes()),0o755)
  changes[catalog.DRIVER_CONTRACT_PATH]=(contract.driver_contract((root/catalog.DRIVER_CONTRACT_PATH).read_bytes(),hashes),0o644)
  changes['usr/sbin/om-radar-engine-f341']=(a.engine.read_bytes(),0o755)
  radio_control=(root/'usr/sbin/om-radioctl').read_bytes()
  changes['usr/sbin/om-radioctl']=(catalog.radio_control_bytes(radio_control).replace(b'f325-diagnostic-profile-locked-reboot-required',b'f341-diagnostic-profile-locked-reboot-required'),0o755)
  for name,row in rows.items():
   p=a.module_dir/(name+'.ko')
   if web.sha256(p)!=row['sha256']:raise ValueError('module drift '+name)
   changes[MODULE_DIR+'/'+name+'.ko']=(p.read_bytes(),0o644)
  new_catalog=contract.catalog(old_catalog,{path:content for path,(content,mode) in changes.items()})
  changes[catalog.ARTIFACTS_PATH]=(new_catalog,0o644)
  expected={path:put(root,path,content,mode) for path,(content,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected);web.check_legacy_asset_metadata(root)
  before_pack=catalog.verify_artifact_catalog(root,new_catalog)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);delta=web.validate_delta(before,after,expected);web.check_legacy_asset_metadata(verified)
  after_unpack=catalog.verify_artifact_catalog(verified,new_catalog)
  # The complete inventory check preserves all secrets, calibration, UI and
  # F340 supervisor bytes outside the exact declared change set.
  for path in before:
   if path not in expected and before[path]!=after.get(path):raise ValueError('unrelated F340 path changed '+path)
  shutil.copyfile(packed,a.image)
  report={'schema':'openmitrastar.f341-rootfs/v1','before':before,'after':after,'checks':delta,'expected_changes':expected,'catalog_verification':{'source':source_catalog,'before_pack':before_pack,'after_unpack':after_unpack},'hardware_actions':False,'acquisition_auto_started':False,'wifi_physical':'USER_DEFERRED'}
  a.result.write_text(json.dumps(report,sort_keys=True)+'\n',encoding='ascii')
if __name__=='__main__':main()
