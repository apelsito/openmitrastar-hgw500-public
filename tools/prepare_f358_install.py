"""Qualify only the F358/F340 adaptation of the already-proven F346 installer."""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil,subprocess,sys
import f358_install_contract as c
import f358_install_executor as executor
import f346_powershell as desktop_ps
from f325_existing_permission_contract import validate_permission,PERMISSION,PERMISSION_SHA,PROGRAM
def main():
 c.require(shutil.disk_usage('C:/').free>500*1024*1024 and shutil.disk_usage('D:/').free>500*1024*1024,'disk_admission_floor')
 images=c.images();protected=c.protected_backups();proofs=c.validate_proofs();binding=c.binding()
 c.EVIDENCE_ROOT.mkdir(parents=True,exist_ok=True)
 for p in (c.EVIDENCE_ROOT,*c.EVIDENCE_ROOT.parents):c.require(not p.is_symlink() and not getattr(p,'is_junction',lambda:False)(),'evidence_reparse')
 out=c.ROOT/'outputs/preflight'/('f358-install-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
 files={Path(m.__file__).resolve() for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(c.ROOT/'tools')}
 files.update(c.ROOT/'tools'/name for name in ['derive_f358_installer.py','test_f358_install.py','f358_install_test_fixture.py','test_f358_context.ps1','run_f358_install.py','run_f358_install.ps1','f358_hardware_context.ps1','assert_f358_context.ps1','prepare_f358_install.py','f321_mtd4_runtime.ps1','f321_process_job.cs','f321_native_job_launcher.ps1','f319_uart_guard.ps1','f319_recovery_guard.ps1','f321_ssh_guard.ps1','f325_existing_firewall.ps1','f336_host_network.ps1','post_flash_f214_device_gate.py','f346_install_executor.py','test_f346_install.py'])
 files.update(c.ROOT/'work/pydeps/serial'/name for name in ['__init__.py','serialutil.py','serialwin32.py','win32.py'])
 files.update([c.BINDING,PERMISSION,Path(protected['manifest'])]);files.update(Path(p['path']) for p in protected['parts']);files.update(Path(p['path']) for p in proofs)
 for image in images.values():files.update([Path(image['path']),Path(image['directory'])/'manifest.json',Path(image['known_hosts_path'])])
 branch=json.loads(Path(proofs[2]['path']).read_text(encoding='ascii'));files.update(Path(p) for p in branch['sources'])
 previous=c.ROOT/'outputs/preflight/f346-install-20260921T150921Z';files.update([previous/'plan.json',previous/'result.json',previous/'python-tests.json',previous/'context-tests.json'])
 for item in binding.get('additional_pins',[]):path=Path(item['path']);c.require(c.sha(path)==item['sha256'],'additional_artifact_drift');files.add(path)
 pins={str(path):c.sha(path) for path in sorted(files)}
 jobs=[([PROGRAM,str(c.ROOT/'tools/test_f358_install.py'),'--result',str(out/'profile-tests.json')],'profile-tests'),([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f358_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context-tests')]
 for args,name in jobs:
  run=subprocess.run(args,env=desktop_ps.environment() if name=='context-tests' else None,capture_output=True,timeout=180);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr)
  if run.returncode:(out/'result.json').write_text(json.dumps(dict(status='FAIL_ADAPTATION_TESTS',test=name,hardware_actions=False),indent=2)+'\n',encoding='ascii')
  c.require(run.returncode==0,name+'_failed')
 tests={}
 for name,count in [('profile',8),('context',7)]:
  path=out/(name+'-tests.json');r=json.loads(path.read_text(encoding='ascii'));c.require(r['passed'] is True and r['tests']==count,'test_count');tests[name]=dict(path=str(path),sha256=c.sha(path),count=count)
 c.require(all(c.sha(path)==digest for path,digest in pins.items()),'source_drift_during_tests')
 permission=validate_permission(PERMISSION,PERMISSION_SHA,python_executable=PROGRAM)
 plan=dict(schema='openmitrastar.f358-install-plan/v1',status='PASS_OFFLINE_REVIEWED_EXECUTOR',created_at_utc=datetime.now(timezone.utc).isoformat(),images=images,protected=protected,proofs=proofs,sources=pins,tests=tests,
  write_target='mtd4/linux_live',offset=c.LIVE,erase_bytes=c.PREFIX,slot_bytes=c.SLOT,store_offset=c.STORE,store_bytes=c.STORE_BYTES,erased_prefix_crc32=c.crc(b'\xff'*c.PREFIX),erased_store_crc32=c.crc(b'\xff'*c.STORE_BYTES),bootargs=c.BOOTARGS,
  evidence_root=str(c.EVIDENCE_ROOT.resolve()),known_hosts=images['f340']['known_hosts_path'],uart_pnp_device_id=c.PNP,physical_lock_dir=str(c.ROOT/'outputs/locks/f301-physical-radio.lock'),
  network=dict(firewall_mode='existing-permission',existing_permission=permission,server_ipv4='192.168.1.49',client_ipv4='192.168.1.90',interface_index=18,interface_alias='Ethernet',python_executable=PROGRAM),
  original_installer=dict(plan=str(previous/'plan.json'),sha256=c.sha(previous/'plan.json'),original_tests=39,rerun_full_battery=False,flash_engine_ast_unchanged=True),
  success_policy='keep_f358_after_exact_readback_new_boot_platform27_and_inactive_watchdog',failure_policy='one_exact_f340_restore_or_prewrite_readonly_return_after_safe_fresh_domain',
  hardware_actions=False,physical_authorization_claimed_by_plan=False,watchdog_arm_allowed=False,radio_tests_allowed=False,aelita_access_allowed=False,boot_environment_persistence_allowed=False,global_protection_or_wpsel_allowed=False,
  limits=['Only physical mtd4 prefix0x5e0000; never store or protected partitions','No other RAM campaign or SPI OBSERVE in this installer','Unknown erase/write completion prohibits automatic retry/rollback','Transfer/network checks stay outside erase-to-program commit dependency','Primary Windows PowerShell5.1 path fixed by run_f358_install.py; no PS7 date conversion','Private F340 backup ACL applied before image copy; public output contains receipt only','Physical SPI observation/persistence are not proven merely by installing this image'])
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=c.sha(path);executor.load_plan(path,digest)
 for args,name in [([PROGRAM,str(c.ROOT/'tools/run_f358_install.py'),'--plan',str(path),'--plan-sha256',digest],'default-launcher'),([PROGRAM,str(c.ROOT/'tools/f358_install_executor.py'),'--plan',str(path),'--plan-sha256',digest],'default-worker')]:
  run=subprocess.run(args,capture_output=True,timeout=90);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr);c.require(run.returncode==0 and not run.stderr,name+'_failed')
 summary=dict(status='PASS_OFFLINE_F358_INSTALLER',plan=str(path),plan_sha256=digest,adaptation_tests=15,original_tests_reused=39,source_pins=len(pins),candidate_sha256=images['f358']['sha256'],fallback_sha256=images['f340']['sha256'],evidence_root=str(c.EVIDENCE_ROOT),default_entrypoints_read_only=True,hardware_actions=False)
 (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='ascii');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
