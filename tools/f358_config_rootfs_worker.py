"""Repack private F340 with an available, unstarted configuration backend."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile
import lyoko_web_rootfs_worker as web
from f334_shadow_rootfs_worker import put
from f334_shadow_contract import verify_artifact_catalog,ARTIFACTS_PATH
PRODUCT_VERSION='lyoko-foundation-6.9.8-f358-config-backend-device'
ROOTFS_SHA='44cc6c3322375ae5d7a97cb5e8af5e458a7d1dc435fa4ccbd9b444ff2cced558'
MODULE='lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn_f356_journal.ko'
SUPERVISOR='usr/sbin/om-watchdog-supervisor'
CLI='usr/sbin/om-journal-cli'
WDTPROFILE='usr/share/openmitrastar/watchdog/profile.json'
STORAGEPROFILE='usr/share/openmitrastar/storage/profile.json'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 for n in ['source','provider','supervisor','cli','image','result']:ap.add_argument('--'+n,type=Path,required=True)
 ap.add_argument('--supervisor-sha256',required=True);ap.add_argument('--build-id',required=True);ap.add_argument('--epoch',type=int,required=True);a=ap.parse_args()
 if os.name!='posix' or os.geteuid()!=0 or a.image.exists() or a.result.exists():raise ValueError('isolated Linux/new outputs required')
 if sha(a.source.read_bytes())!=ROOTFS_SHA or not re.fullmatch('[0-9a-f]{16}',a.build_id):raise ValueError('F340 source/build identity')
 provider=a.provider.read_bytes();supervisor=a.supervisor.read_bytes();cli=a.cli.read_bytes()
 expected_hashes=['ab88ec603c18cd013f0de1d79eed1ea9c696ca97d2b589e0e8b9aaa8f9251cd4',a.supervisor_sha256,'dee84fd30d41734e52d4627418028a1d15cd64db87cca1bc3eef261aacb0edef']
 if [sha(provider),sha(supervisor),sha(cli)]!=expected_hashes:raise ValueError('qualified component drift')
 with tempfile.TemporaryDirectory(prefix='f358-rootfs-',dir='/tmp') as directory:
  scratch=Path(directory);root=scratch/'root';verified=scratch/'verified';packed=scratch/'rootfs.squashfs'
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(root),str(a.source)],check=True,stdout=subprocess.DEVNULL)
  before=web.inventory(root);radio_catalog=(root/ARTIFACTS_PATH).read_bytes();radio_before=verify_artifact_catalog(root,radio_catalog)
  if sha((root/'etc/openmitrastar/release').read_bytes())!='ad0cce812937b68ae41b0a729a5c410d5666c4052ea2ccf6e0f0e5cba12e8318':raise ValueError('F340 release drift')
  changes={'OPENMITRASTAR_PRODUCT_VERSION':PRODUCT_VERSION,'OPENMITRASTAR_BUILD_ID':a.build_id}
  release=(root/'etc/openmitrastar/release').read_text().splitlines()
  for key in changes:
   if sum(line.startswith(key+'=') for line in release)!=1:raise ValueError('release cardinality')
  release=('\n'.join(line.split('=',1)[0]+'='+changes[line.split('=',1)[0]] if line.split('=',1)[0] in changes else line for line in release)+'\n').encode()
  wdt=json.dumps({'schema':'openmitrastar.f358-watchdog-profile/v1','kernel_version':'#358 @1790006400','kernel_release':'5.10.260-openmitrastar-radiohw','kernel_marker':'F340_WATCHDOG_BASELINE','supervisor_sha256':sha(supervisor),'automatic_arm':False,'init_script_installed':False,'session_max_ms':180000,'phase_max_ms':60000,'timeout_reported_seconds':8,'sole_owner':'explicit-supervisor-process-fd','cease':'hold-fd-without-pets-until-reset','disarm_supported':False},sort_keys=True,indent=2).encode()+b'\n'
  storage=json.dumps({'schema':'openmitrastar.f358-config-backend-profile/v1','module':'/'+MODULE,'module_name':'qtn_f356_journal','module_sha256':sha(provider),'cli':'/'+CLI,'cli_sha256':sha(cli),'device':'/dev/om-f350-journal','kernel_version':'#358 @1790006400','autoload':False,'startup_mmio':False,'automatic_writes':False,'default_allow_hw':False,'default_allow_program':False,'activation':'separate explicit owner campaign','loader':'/usr/sbin/ram-insmod-qtn','payload_max':4096,'reserved_blocks':['0xdc0000','0xdd0000'],'protection_policy':'observed common BP0 only, never unlock'},sort_keys=True,indent=2).encode()+b'\n'
  wdt_catalog=(sha(supervisor)+'  /'+SUPERVISOR+'\n'+sha(wdt)+'  /'+WDTPROFILE+'\n').encode()
  storage_catalog=''.join(sha(data)+'  /'+name+'\n' for name,data in [(MODULE,provider),(CLI,cli),(STORAGEPROFILE,storage)]).encode()
  delta={'etc/openmitrastar/release':(release,0o644),SUPERVISOR:(supervisor,0o755),WDTPROFILE:(wdt,0o644),'usr/share/openmitrastar/watchdog/artifacts.sha256':(wdt_catalog,0o644),MODULE:(provider,0o644),CLI:(cli,0o755),STORAGEPROFILE:(storage,0o644),'usr/share/openmitrastar/storage/artifacts.sha256':(storage_catalog,0o644)}
  expected={name:put(root,name,data,mode) for name,(data,mode) in delta.items()}
  web.validate_delta(before,web.inventory(root),expected);web.check_legacy_asset_metadata(root)
  subprocess.run(['mksquashfs',str(root),str(packed),'-noappend','-all-root','-comp','xz','-b','131072','-no-xattrs','-no-exports','-all-time',str(a.epoch),'-mkfs-time',str(a.epoch),'-processors','1','-no-progress'],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['unsquashfs','-processors','1','-no-progress','-d',str(verified),str(packed)],check=True,stdout=subprocess.DEVNULL)
  after=web.inventory(verified);checks=web.validate_delta(before,after,expected);web.check_legacy_asset_metadata(verified)
  unchanged=[p for p in before if p.startswith(('etc/init.d/','lib/modules/','usr/share/openmitrastar/device-identity/')) or p in ('usr/sbin/om-radio5-start','usr/sbin/om-radio5-stop','usr/sbin/om-radioctl','usr/libexec/openmitrastar/om-api-v1','usr/share/openmitrastar/radio5g/driver-contract.env','usr/sbin/ram-insmod-qtn')]
  if any(before[p]!=after[p] for p in unchanged) or (verified/ARTIFACTS_PATH).read_bytes()!=radio_catalog:raise ValueError('protected F340 runtime changed')
  radio_after=verify_artifact_catalog(verified,radio_catalog)
  for name,(content,mode) in delta.items():
   if (verified/name).read_bytes()!=content:raise ValueError('repacked component changed '+name)
  shutil.copyfile(packed,a.image)
  a.result.write_text(json.dumps({'schema':'openmitrastar.f358-rootfs/v1','before':before,'after':after,'expected_changes':expected,'checks':checks,'changed_files':sorted(delta),'all_init_scripts_unchanged':True,'original_modules_unchanged':True,'protected_entries_unchanged':len(unchanged),'radio_catalog_before':radio_before,'radio_catalog_after':radio_after,'backend_autoload':False,'watchdog_automatic_arm':False,'startup_mmio_or_writes':False},sort_keys=True)+'\n')
if __name__=='__main__':main()
