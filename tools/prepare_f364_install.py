"""Seal the minimal F364 target/store/serial-recovery adaptation."""
from pathlib import Path
from datetime import datetime,timezone
import json,shutil,subprocess,sys
import f364_install_contract as c
import f364_install_executor as executor
import f346_powershell as desktop_ps
from f325_existing_permission_contract import validate_permission,PERMISSION,PERMISSION_SHA,PROGRAM
def main():
 c.require(shutil.disk_usage('C:/').free>500*1024*1024 and shutil.disk_usage('D:/').free>500*1024*1024,'disk_admission_floor')
 store=c.store_binding();images=c.images();protected=c.protected_backups();proofs=c.validate_proofs();binding=c.binding();c.EVIDENCE_ROOT.mkdir(parents=True,exist_ok=True)
 for path in (c.EVIDENCE_ROOT,*c.EVIDENCE_ROOT.parents):c.require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'evidence_reparse')
 out=c.ROOT/'outputs/preflight'/('f364-install-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
 files={Path(m.__file__).resolve() for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(c.ROOT/'tools')}
 files.update(c.ROOT/'tools'/name for name in ['derive_f364_installer.py','prepare_f364_install.py','test_f364_install_delta.py','test_f364_context.ps1','run_f364_install.py','run_f364_install.ps1','f364_hardware_context.ps1','assert_f364_context.ps1','f321_mtd4_runtime.ps1','f321_process_job.cs','f321_native_job_launcher.ps1','f319_uart_guard.ps1','f319_recovery_guard.ps1','f321_ssh_guard.ps1','f325_existing_firewall.ps1','f336_host_network.ps1','post_flash_f214_device_gate.py'])
 files.update(c.ROOT/'work/pydeps/serial'/name for name in ['__init__.py','serialutil.py','serialwin32.py','win32.py'])
 files.update([c.BINDING,c.BASELINE,c.STORE_BINDING,Path(store['path']),Path(store['physical_result']['path']),PERMISSION,Path(protected['manifest'])]);files.update(Path(v['path']) for v in protected['parts']);files.update(Path(v['path']) for v in proofs)
 audit=json.loads(Path(store['erase_audit']['path']).read_text(encoding='ascii'));files.update(Path(p) for p in audit['sources'])
 for image in images.values():files.update([Path(image['path']),Path(image['directory'])/'manifest.json',Path(image['known_hosts_path'])])
 # Reuse Ethernet acceptance; pin only the thermal wrapper source delta.
 files.update(c.ROOT/'work/kernel-port/modules/f352_dual_emac'/p for p in ['qtn-topaz-emac-f352.c','f352_pair.inc'])
 files.add(c.ROOT/'work/kernel-port/versions/f363-temperature-diagnostic/temp_sens.c')
 files.add(c.ROOT/'tools/test_f364_ethernet_identity.py');files.add(Path('/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/f363.dtb'))
 pins={str(path):c.sha(path) for path in sorted(files)};tests={}
 for args,name,count in [([PROGRAM,str(c.ROOT/'tools/test_f364_install_delta.py'),'--result',str(out/'delta-tests.json')],'delta',3),([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f364_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context',4),([PROGRAM,str(c.ROOT/'tools/test_f364_ethernet_identity.py'),'--result',str(out/'ethernet-identity-tests.json')],'ethernet-identity',6)]:
  run=subprocess.run(args,env=desktop_ps.environment() if name=='context' else None,capture_output=True,timeout=120);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr);c.require(run.returncode==0,name+'_tests_failed')
  path=out/(name+'-tests.json');r=json.loads(path.read_text(encoding='ascii'));c.require(r['passed'] and r['tests']==count,'test_result');tests[name]=dict(path=str(path),sha256=c.sha(path),count=count)
 c.require(all(c.sha(path)==h for path,h in pins.items()),'source_drift')
 permission=validate_permission(PERMISSION,PERMISSION_SHA,python_executable=PROGRAM)
 plan=dict(schema='openmitrastar.f364-install-plan/v1',status='PASS_OFFLINE_REVIEWED_EXECUTOR',images=images,store=store,protected=protected,proofs=proofs,sources=pins,tests=tests,boot_acceptance=binding['boot_acceptance'],serial_recovery=binding['serial_recovery'],baseline_proofs=c.baseline_binding(),
  thermal_default=binding['thermal_default'],sensor_activation_allowed=False,
  write_target='mtd4/linux_live',offset=c.LIVE,erase_bytes=c.PREFIX,erase_end_exclusive=c.STORE,slot_bytes=c.SLOT,store_offset=c.STORE,store_bytes=c.STORE_BYTES,erased_prefix_crc32=c.crc(b'\xff'*c.PREFIX),bootargs=c.BOOTARGS,evidence_root=str(c.EVIDENCE_ROOT.resolve()),known_hosts=images['f363']['known_hosts_path'],uart_pnp_device_id=c.PNP,physical_lock_dir=str(c.ROOT/'outputs/locks/f301-physical-radio.lock'),
  network=dict(firewall_mode='existing-permission',existing_permission=permission,server_ipv4='192.168.1.49',client_ipv4='192.168.1.90',interface_index=18,interface_alias='Ethernet',python_executable=PROGRAM),
  success_policy='F364 platform27, dual Ethernet verified from bound DT properties and live IRQ/bridge/carrier without boot-log dependence, and seq2 store unchanged; thermal cached state is disabled with no activation attempt. No temperature sampling or activation.',
  failure_policy='One serial BREAK+b from a fresh Linux UART epoch, new Bootbase prompt, restore F363 prefix only. No repeat after ambiguous serial or flash completion. Store mismatch blocks every write.',
  hardware_actions=False,watchdog_arm_allowed=False,radio_tests_allowed=False,boot_environment_persistence_allowed=False,store_write_allowed=False,
  limits=['Second physical connector traffic is not tested without moving cables','Serial SysRq requires a responsive Linux UART/IRQ path; no CPU/bus-halt claim','Candidate and rollback fullslot include exact seq2 store; no FF assumption','Existing F363 transport/writer tests reused without rerunning their general battery'])
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=c.sha(path);executor.load_plan(path,digest)
 for args,name in [([PROGRAM,str(c.ROOT/'tools/run_f364_install.py'),'--plan',str(path),'--plan-sha256',digest],'default-launcher'),([PROGRAM,str(c.ROOT/'tools/f364_install_executor.py'),'--plan',str(path),'--plan-sha256',digest],'default-worker')]:
  run=subprocess.run(args,capture_output=True,timeout=90);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr);c.require(run.returncode==0 and not run.stderr,name+'_failed')
 r=dict(status='PASS_OFFLINE_F364_LIFETIME_INSTALLER',plan=str(path),plan_sha256=digest,adaptation_tests=13,source_pins=len(pins),hardware_actions=False,candidate_full_slot_crc32=images['f364']['full_slot_crc32'],fallback_full_slot_crc32=images['f363']['full_slot_crc32'],preserved_store_crc32=store['crc32']);(out/'result.json').write_text(json.dumps(r,indent=2)+'\n',encoding='ascii');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
