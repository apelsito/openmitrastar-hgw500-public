"""Small live-F358 adaptation qualification; no hardware, RAM boot or TFTP."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,sys
import f359_observe_executor as executor
import f358_install_contract as c
import f346_powershell as desktop_ps

INSTALL=Path('/workspace/OpenMitraStar/f358-evidence/f358-install-20260921T175118Z-31a39fbd/result.json')
INSTALL_SHA='3540e48cf0d0c7bd9bf8fd15a2029f7b0b95cb6c29ea8162c2fb5d6c1ac3d49f'
def main():
 executor.disk_floor();c.require(c.sha(INSTALL)==INSTALL_SHA,'installed_proof_drift');installed=json.loads(INSTALL.read_text(encoding='ascii'))
 c.require(installed['status']=='PASS_F358_PERSISTENT_BASELINE' and installed['platform']['checks']==27 and installed['writer']['full_slot_crc32']=='4d006632' and installed['writer']['byte_compare'] is True and installed['watchdog']['ready_for_arm']==1 and installed['containment_confirmed'] is True and installed['retain_lease_required'] is False,'installed_f358_required')
 images={'f358':c.images()['f358']};image=images['f358'];protected=c.protected_backups();manifest=Path(image['directory'])/'manifest.json';mf=json.loads(manifest.read_text(encoding='ascii'))
 bundle_path=c.ROOT/'outputs/kernel-port/f356-observe-ram-20260921T171309Z/result.json';bundle=json.loads(bundle_path.read_text(encoding='ascii'));c.require(c.sha(bundle_path)=='5ae7ad32f718da536787cb1008450a24ce4551861245ca3c64a5ebcf89fe7d0f','provider_bundle')
 sr_path=c.ROOT/'outputs/kernel-port/f358-supervisor-20260921T174119Z/result.json';sr=json.loads(sr_path.read_text(encoding='ascii'));supervisor=sr['artifact'];provider=bundle['provider'];cli=bundle['cli'];loader=bundle['loader']
 c.require(supervisor['sha256']==mf['watchdog']['supervisor_sha256']==executor.SUPERVISOR_SHA and mf['watchdog']['automatic_arm'] is False,'installed_supervisor')
 c.require(provider['sha256']==mf['config_backend']['module_sha256'] and cli['sha256']==mf['config_backend']['cli_sha256'] and mf['config_backend']['autoload'] is False,'installed_provider_cli')
 files={Path(m.__file__).resolve() for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(c.ROOT/'tools')}
 for item in (supervisor,provider,cli,loader):c.require(c.sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes'],'component_hash');files.add(Path(item['path']))
 for path,digest in sr['sources'].items():c.require(c.sha(path)==digest,'supervisor_source_drift');files.add(Path(path))
 files.update(c.ROOT/'tools'/name for name in ['derive_f359_executor.py','f359_executor_header.inc','f359_executor_footer.inc','prepare_f359_observe.py','test_f359_profile.py','test_f359_context.ps1','test_f356_observe.py','run_f359_observe.py','run_f359_observe.ps1','f359_hardware_context.ps1','assert_f359_context.ps1','f321_mtd4_runtime.ps1','f321_process_job.cs','f321_native_job_launcher.ps1','f319_uart_guard.ps1','f319_recovery_guard.ps1','f321_ssh_guard.ps1','f336_host_network.ps1','post_flash_f214_device_gate.py'])
 files.update(c.ROOT/'work/pydeps/serial'/name for name in ['__init__.py','serialutil.py','serialwin32.py','win32.py'])
 files.update([INSTALL,manifest,Path(image['path']),Path(image['known_hosts_path']),c.BINDING,bundle_path,sr_path,Path(protected['manifest']),c.ROOT/'outputs/preflight/f356-observe-20260921T171932Z/plan.json',c.ROOT/'outputs/preflight/f356-observe-20260921T171932Z/result.json'])
 files.update(Path(item['path']) for item in protected['parts']);pins={str(path):c.sha(path) for path in sorted(files)}
 executor.EVIDENCE_ROOT.mkdir(parents=True,exist_ok=True)
 for path in (executor.EVIDENCE_ROOT,*executor.EVIDENCE_ROOT.parents):c.require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'evidence_reparse')
 out=c.ROOT/'outputs/preflight'/('f359-observe-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
 jobs=[([sys.executable,str(c.ROOT/'tools/test_f359_profile.py'),'--result',str(out/'profile-tests.json')],'profile-tests'),([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f359_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context-tests')]
 for args,name in jobs:
  r=subprocess.run(args,env=desktop_ps.environment() if name=='context-tests' else None,capture_output=True,timeout=120);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
  if r.returncode:executor.save(out/'result.json',dict(status='FAIL_PROFILE_TESTS',test=name,hardware_actions=False))
  c.require(r.returncode==0,name+'_failed')
 tests={}
 for name in ('profile','context'):
  path=out/(name+'-tests.json');r=json.loads(path.read_text(encoding='ascii'));c.require(r['passed'] is True and r['tests']==4,'test_count');tests[name]=dict(path=str(path),sha256=c.sha(path),count=4)
 c.require(all(c.sha(path)==digest for path,digest in pins.items()),'source_drift_during_tests')
 plan=dict(schema='openmitrastar.f359-observe-plan/v1',status='PASS_OFFLINE_LIVE_OBSERVE_GATE',images=images,protected=protected,bootargs=c.BOOTARGS,provider=provider,cli=cli,supervisor=supervisor,loader=loader,sources=pins,tests=tests,
  installed_proof=dict(path=str(INSTALL),sha256=INSTALL_SHA),expected_spi_control=4,observation_commands=['observe'],allow_program=False,one_shot=True,ram_kernel_boot=False,tftp_allowed=False,save_allowed=False,hardware_actions=False,radio_actions=False,
  known_hosts=image['known_hosts_path'],uart_pnp_device_id=c.PNP,physical_lock_dir=str(c.ROOT/'outputs/locks/f301-physical-radio.lock'),evidence_root=str(executor.EVIDENCE_ROOT.resolve()),
  network=dict(server_ipv4='192.168.1.49',client_ipv4='192.168.1.90',interface_index=18,interface_alias='Ethernet',python_executable=sys.executable),
  success_policy='One validated CLI OBSERVE and matching post-release UART marker; one unload, CEASE/reset and exact read-only F358 return with platform27 and inactive watchdog.',
  failure_policy='Never repeat OBSERVE; failed/partial/quarantined means no unload, CEASE/reset and F358 read-only return. No kernel RAM boot, TFTP or program/erase command.',
  original_mechanisms='F354/F356 owner, loader, capture, marker, one-shot and recovery reused; F358 installed profile only. Historical batteries not repeated.',
  limits=['Supervisor/CLI copied from hash-verified installed files into /run so quarantine cannot fault their code from rootfs','ID c22018 does not distinguish 35F versus36E','No SAVE/PP/D8/protection writes; only the existing ID-gated SCUR control sequence','No CPU/bus halt or WiFi/client test'])
 path=out/'plan.json';executor.save(path,plan);digest=c.sha(path);executor.load_plan(path,digest)
 for args,name in [([sys.executable,str(c.ROOT/'tools/run_f359_observe.py'),'--plan',str(path),'--plan-sha256',digest],'default-launcher'),([sys.executable,str(c.ROOT/'tools/f359_observe_executor.py'),'--plan',str(path),'--plan-sha256',digest],'default-worker')]:
  r=subprocess.run(args,capture_output=True,timeout=90);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);c.require(r.returncode==0 and not r.stderr,name+'_failed')
 summary=dict(status='PASS_OFFLINE_F359_LIVE_PROFILE',plan=str(path),plan_sha256=digest,adaptation_tests=8,source_pins=len(pins),evidence_root=str(executor.EVIDENCE_ROOT),hardware_actions=False,ram_kernel_boot=False,tftp_allowed=False,historical_batteries_rerun=False)
 executor.save(out/'result.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
