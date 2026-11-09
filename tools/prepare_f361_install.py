"""Seal a concrete F361 image while preserving the physically verified journal."""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil,subprocess,sys
import f361_install_contract as c
import f361_install_executor as executor
import f346_powershell as desktop_ps
from f325_existing_permission_contract import validate_permission,PERMISSION,PERMISSION_SHA,PROGRAM
def main():
 c.require(shutil.disk_usage('C:/').free>500*1024*1024 and shutil.disk_usage('D:/').free>500*1024*1024,'disk_admission_floor')
 store=c.store_binding();images=c.images();protected=c.protected_backups();proofs=c.validate_proofs();binding=c.binding()
 c.require(images['f358']['full_slot_crc32']=='3e8db0dc' and images['f358']['manifest_ff_full_slot_crc32']=='4d006632','fallback_store_not_included')
 c.EVIDENCE_ROOT.mkdir(parents=True,exist_ok=True)
 for path in (c.EVIDENCE_ROOT,*c.EVIDENCE_ROOT.parents):c.require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'evidence_reparse')
 out=c.ROOT/'outputs/preflight'/('f361-install-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
 files={Path(m.__file__).resolve() for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(c.ROOT/'tools')}
 files.update(c.ROOT/'tools'/name for name in ['derive_f361_installer.py','prepare_f361_store_and_erase.py','prepare_f361_install.py','test_f361_preserve_store.py','f361_install_test_fixture.py','test_f361_context.ps1','run_f361_install.py','run_f361_install.ps1','f361_hardware_context.ps1','assert_f361_context.ps1','f321_mtd4_runtime.ps1','f321_process_job.cs','f321_native_job_launcher.ps1','f319_uart_guard.ps1','f319_recovery_guard.ps1','f321_ssh_guard.ps1','f325_existing_firewall.ps1','f336_host_network.ps1','post_flash_f214_device_gate.py'])
 files.update(c.ROOT/'work/pydeps/serial'/name for name in ['__init__.py','serialutil.py','serialwin32.py','win32.py'])
 files.update([c.BINDING,c.STORE_BINDING,Path(store['path']),Path(store['physical_result']['path']),Path(store['erase_audit']['path']),PERMISSION,Path(protected['manifest'])])
 files.update(Path(v['path']) for v in store['captured_parts']);files.update(Path(v['path']) for v in protected['parts']);files.update(Path(v['path']) for v in proofs)
 audit=json.loads(Path(store['erase_audit']['path']).read_text(encoding='ascii'));files.update(Path(p) for p in audit['sources'])
 for image in images.values():files.update([Path(image['path']),Path(image['directory'])/'manifest.json',Path(image['known_hosts_path'])])
 for pin in binding.get('additional_pins',[]):c.require(pin['sha256']==c.sha(pin['path']),'additional_source_drift');files.add(Path(pin['path']))
 pins={str(path):c.sha(path) for path in sorted(files)}
 jobs=[([PROGRAM,str(c.ROOT/'tools/test_f361_preserve_store.py'),'--result',str(out/'store-tests.json')],'store-tests'),([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f361_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context-tests')]
 for args,name in jobs:
  run=subprocess.run(args,env=desktop_ps.environment() if name=='context-tests' else None,capture_output=True,timeout=180);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr)
  if run.returncode:(out/'result.json').write_text(json.dumps(dict(status='FAIL_STORE_ADAPTATION_TESTS',test=name,hardware_actions=False),indent=2)+'\n',encoding='ascii')
  c.require(run.returncode==0,name+'_failed')
 tests={}
 for name,count in [('store',5),('context',4)]:
  path=out/(name+'-tests.json');data=json.loads(path.read_text(encoding='ascii'));c.require(data['passed'] is True and data['tests']==count,'test_count');tests[name]=dict(path=str(path),sha256=c.sha(path),count=count)
 c.require(all(c.sha(path)==digest for path,digest in pins.items()),'source_drift_during_tests')
 permission=validate_permission(PERMISSION,PERMISSION_SHA,python_executable=PROGRAM)
 plan=dict(schema='openmitrastar.f361-install-plan/v1',status='PASS_OFFLINE_REVIEWED_EXECUTOR',images=images,store=store,protected=protected,proofs=proofs,sources=pins,tests=tests,boot_acceptance=binding['boot_acceptance'],
  write_target='mtd4/linux_live',offset=c.LIVE,erase_bytes=c.PREFIX,erase_end_exclusive=c.STORE,slot_bytes=c.SLOT,store_offset=c.STORE,store_bytes=c.STORE_BYTES,erased_prefix_crc32=c.crc(b'\xff'*c.PREFIX),bootargs=c.BOOTARGS,
  evidence_root=str(c.EVIDENCE_ROOT.resolve()),known_hosts=images['f358']['known_hosts_path'],uart_pnp_device_id=c.PNP,physical_lock_dir=str(c.ROOT/'outputs/locks/f301-physical-radio.lock'),
  network=dict(firewall_mode='existing-permission',existing_permission=permission,server_ipv4='192.168.1.49',client_ipv4='192.168.1.90',interface_index=18,interface_alias='Ethernet',python_executable=PROGRAM),
  success_policy='Install firmware prefix only; preserve exact committed store before, immediately after erase, after program and after boot. Candidate and F358 rollback fullslot checksums include the same store snapshot.',
  failure_policy='Known failed candidate may restore only F358 firmware prefix while keeping store unchanged. Store drift stops all writes; unknown command completion never retries.',
  hardware_actions=False,watchdog_arm_allowed=False,radio_tests_allowed=False,boot_environment_persistence_allowed=False,store_write_allowed=False,
  limits=['Manifest fullslot CRC values based on FF padding are reference metadata only','No store erase/program or normalization; payload is never appended to the TFTP firmware image','Rollback F358 operational CRC is3e8db0dc with journal, not4d006632','A newer legitimate journal requires a new private binding; this plan never discards it','Single static Bootbase audit proves the end is exclusive, and runtime non-FF store checks remain mandatory'])
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=c.sha(path);executor.load_plan(path,digest)
 for args,name in [([PROGRAM,str(c.ROOT/'tools/run_f361_install.py'),'--plan',str(path),'--plan-sha256',digest],'default-launcher'),([PROGRAM,str(c.ROOT/'tools/f361_install_executor.py'),'--plan',str(path),'--plan-sha256',digest],'default-worker')]:
  run=subprocess.run(args,capture_output=True,timeout=90);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr);c.require(run.returncode==0 and not run.stderr,name+'_failed')
 summary=dict(status='PASS_OFFLINE_F361_JOURNAL_PRESERVING_INSTALLER',plan=str(path),plan_sha256=digest,adaptation_tests=9,source_pins=len(pins),preserved_store_sha256=store['sha256'],preserved_store_crc32=store['crc32'],candidate_full_slot_crc32=images['f361']['full_slot_crc32'],fallback_full_slot_crc32=images['f358']['full_slot_crc32'],hardware_actions=False,default_entrypoints_read_only=True)
 (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='ascii');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
