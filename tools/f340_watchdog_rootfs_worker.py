"""Repack exact F321 with only the unstarted F340 supervisor and release data."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH,SOURCE_ROOTFS,SOURCE_RELEASE,SOURCE_ARTIFACTS
PRODUCT_VERSION='lyoko-foundation-6.9.6-f340-watchdog-baseline-device'
RELEASE='etc/openmitrastar/release'
SUPERVISOR='usr/sbin/om-watchdog-supervisor'
PROFILE='usr/share/openmitrastar/watchdog/profile.json'
CATALOG='usr/share/openmitrastar/watchdog/artifacts.sha256'
def digest(b):return hashlib.sha256(b).hexdigest()
def run(a):
 if os.name!='posix' or os.geteuid()!=0:raise ValueError('Linux root build environment required')
 if digest(a.source.read_bytes())!=SOURCE_ROOTFS:raise ValueError('F321 rootfs drift')
 if digest(a.supervisor.read_bytes())!=a.supervisor_sha256:raise ValueError('supervisor changed')
 if not re.fullmatch('[0-9a-f]{16}',a.build_id):raise ValueError('build identity')
 if a.image.exists() or a.result.exists():raise ValueError('refusing output overwrite')
 with tempfile.TemporaryDirectory(prefix='f340-watchdog-rootfs-',dir='/tmp') as tmp:
  tmp=Path(tmp);root=tmp/'root';verified=tmp/'verified';packed=tmp/'rootfs.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);catalog=(root/ARTIFACTS_PATH).read_bytes()
  if digest(catalog)!=SOURCE_ARTIFACTS:raise ValueError('radio catalogue drift')
  initial_catalog=verify_artifact_catalog(root,catalog)
  release=(root/RELEASE).read_bytes()
  if digest(release)!=SOURCE_RELEASE:raise ValueError('release drift')
  replacements={'OPENMITRASTAR_PRODUCT_VERSION':PRODUCT_VERSION,'OPENMITRASTAR_BUILD_ID':a.build_id}
  lines=release.decode('ascii').splitlines()
  for key in replacements:
   if sum(line.startswith(key+'=') for line in lines)!=1:raise ValueError('release field cardinality')
  release=('\n'.join(line.split('=',1)[0]+'='+replacements[line.split('=',1)[0]] if line.split('=',1)[0] in replacements else line for line in lines)+'\n').encode()
  profile=(json.dumps({'schema':'openmitrastar.f340-watchdog-profile/v1','automatic_arm':False,'init_script_installed':False,
   'kernel_marker':'F340_WATCHDOG_BASELINE','supervisor_sha256':a.supervisor_sha256,'session_max_ms':180000,'phase_max_ms':60000,
   'timeout_reported_seconds':8,'physical_qualification_required':True,'sole_owner':'supervisor-process-fd',
   'cease':'hold-fd-without-pets-until-reset','disarm_supported':False},sort_keys=True,indent=2)+'\n').encode()
  supervisor=a.supervisor.read_bytes();wdt_catalog=(digest(supervisor)+'  /'+SUPERVISOR+'\n'+digest(profile)+'  /'+PROFILE+'\n').encode()
  changes={RELEASE:(release,0o644),SUPERVISOR:(supervisor,0o755),PROFILE:(profile,0o644),CATALOG:(wdt_catalog,0o644)}
  expected={name:put(root,name,content,mode) for name,(content,mode) in changes.items()}
  web.validate_delta(before,web.inventory(root),expected);web.check_legacy_asset_metadata(root)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);web.check_legacy_asset_metadata(verified)
  final_catalog=verify_artifact_catalog(verified,catalog)
  protected=['usr/sbin/om-radio5-start','usr/sbin/om-radioctl','usr/libexec/openmitrastar/om-api-v1','usr/share/openmitrastar/radio5g/driver-contract.env']
  protected += [p for p in before if p.startswith(('etc/init.d/','lib/modules/','usr/share/openmitrastar/device-identity/'))]
  if any(before[p]!=after[p] for p in protected):raise ValueError('F321 protected runtime changed')
  if (verified/ARTIFACTS_PATH).read_bytes()!=catalog:raise ValueError('F321 radio catalogue changed')
  shutil.copyfile(packed,a.image)
  a.result.write_text(json.dumps({'schema':'openmitrastar.f340-rootfs/v1','before':before,'after':after,'checks':checks,
   'expected_changes':expected,'automatic_arm':False,'all_init_scripts_unchanged':True,'protected_entries_unchanged':len(protected),
   'radio_catalog_before':initial_catalog,'radio_catalog_after':final_catalog},sort_keys=True)+'\n')
def main():
 ap=argparse.ArgumentParser()
 for name in ['source','supervisor','image','result']:ap.add_argument('--'+name,type=Path,required=True)
 ap.add_argument('--supervisor-sha256',required=True);ap.add_argument('--build-id',required=True);ap.add_argument('--epoch',type=int,required=True)
 run(ap.parse_args())
if __name__=='__main__':main()
