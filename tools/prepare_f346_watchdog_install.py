"""Qualify and pin F346 without executing any network/device operation."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,sys
import f346_install_contract as c
import f346_install_executor as executor
import f346_powershell as desktop_ps
from f325_existing_permission_contract import validate_permission,PERMISSION,PERMISSION_SHA,PROGRAM

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=c.ROOT/'outputs/preflight'/('f346-install-'+stamp);out.mkdir(exist_ok=False)
    images=c.images();backups=c.protected_backups();proofs=c.validate_proofs()
    files={Path(module.__file__).resolve() for module in sys.modules.values() if getattr(module,'__file__',None) and Path(module.__file__).resolve().is_relative_to(c.ROOT/'tools')}
    files.update(c.ROOT/'tools'/name for name in ['run_f346_watchdog_install.ps1','f346_hardware_context.ps1','assert_f346_context.ps1','test_f346_install.py','test_f346_context.ps1',
        'f321_mtd4_runtime.ps1','f321_process_job.cs','f321_native_job_launcher.ps1','f319_uart_guard.ps1','f319_recovery_guard.ps1','f321_ssh_guard.ps1','f325_existing_firewall.ps1','f336_host_network.ps1','post_flash_f214_device_gate.py','prepare_f346_watchdog_install.py'])
    files.update(c.ROOT/'work/pydeps/serial'/name for name in ['__init__.py','serialutil.py','serialwin32.py','win32.py'])
    for image in images.values():files.update([Path(image['path']),Path(image['directory'])/'manifest.json',Path(image['known_hosts_path'])])
    files.add(Path(backups['manifest']));files.update(Path(p['path']) for p in backups['parts']);files.update(Path(p['path']) for p in proofs)
    branch=json.loads(Path(proofs[-1]['path']).read_text(encoding='ascii'));files.update(Path(p) for p in branch['sources'])
    pins={str(p):c.sha(p) for p in sorted(files)}
    jobs=[([sys.executable,str(c.ROOT/'tools/test_f346_install.py'),'--result',str(out/'python-tests.json')],'python-tests'),
          ([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f346_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context-tests')]
    for argv,name in jobs:
        run=subprocess.run(argv,env=desktop_ps.environment() if Path(argv[0]).name.lower()=='powershell.exe' else None,capture_output=True,timeout=300)
        (out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr)
        if run.returncode:
            (out/'result.json').write_text(json.dumps(dict(status='FAILED_OFFLINE_TESTS',test=name,returncode=run.returncode,hardware_actions=False),indent=2)+'\n',encoding='ascii')
        c.require(run.returncode==0,name+'_failed')
    py=json.loads((out/'python-tests.json').read_text(encoding='ascii'));ps=json.loads((out/'context-tests.json').read_text(encoding='ascii'))
    c.require(py['passed'] is True and py['tests']==23 and ps['passed'] is True and ps['tests']==16,'test_counts')
    c.require(all(c.sha(p)==h for p,h in pins.items()),'sources_changed_during_tests')
    permission=validate_permission(PERMISSION,PERMISSION_SHA,python_executable=PROGRAM)
    plan=dict(schema='openmitrastar.f346-install-plan/v1',status='PASS_OFFLINE_REVIEWED_EXECUTOR',created_at_utc=datetime.now(timezone.utc).isoformat(),
        images=images,protected=backups,proofs=proofs,sources=pins,tests={'python':{'path':str(out/'python-tests.json'),'sha256':c.sha(out/'python-tests.json'),'count':23},'context':{'path':str(out/'context-tests.json'),'sha256':c.sha(out/'context-tests.json'),'count':16}},
        write_target='mtd4/linux_live',offset=c.LIVE,erase_bytes=c.PREFIX,slot_bytes=c.SLOT,store_offset=c.STORE,store_bytes=c.STORE_BYTES,
        erased_prefix_crc32=c.crc(b'\xff'*c.PREFIX),erased_store_crc32=c.crc(b'\xff'*c.STORE_BYTES),bootargs=c.BOOTARGS,
        known_hosts=images['f321']['known_hosts_path'],uart_pnp_device_id=c.PNP,physical_lock_dir=str(c.ROOT/'outputs/locks/f301-physical-radio.lock'),
        network=dict(firewall_mode='existing-permission',existing_permission=permission,server_ipv4='192.168.1.49',client_ipv4='192.168.1.90',interface_index=18,interface_alias='Ethernet',python_executable=PROGRAM),
        success_policy='keep_f340_after_27_platform_and_inactive_watchdog',failure_policy='one_exact_f321_return_only_after_fresh_safe_domain_and_containment',
        physical_authorization_claimed_by_plan=False,hardware_actions=False,watchdog_arm_allowed=False,radio_tests_allowed=False,aelita_access_allowed=False,
        boot_environment_persistence_allowed=False,global_protection_or_wpsel_allowed=False,
        backup_semantics='Exact local F321 rollback copy plus existing protected backups, bound to fresh Bootbase CRCs; not a new raw full-chip dump or observed hardware SHA256.',
        store_policy='Must match the observed current erased F321 store before installation; no normalization, erase or write of store. Unexpected data refuses the operation.',
        limits=['Firmware manifests remain immutable and do not grant execution','Only explicit -Execute plus live F346 nonce/lease context activates the worker','Ambiguous erase/write completion never triggers an automatic write or reboot','F321 restoration is never retried or redirected to F314','F336 cessation evidence does not prove CPU/bus/full-chip recovery'])
    path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=c.sha(path);executor.load_plan(path,digest)
    for argv,name in [([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/run_f346_watchdog_install.ps1'),'-PlanPath',str(path),'-PlanSha256',digest],'default-powershell'),
                     ([sys.executable,str(c.ROOT/'tools/f346_install_executor.py'),'--plan',str(path),'--plan-sha256',digest],'default-python')]:
        run=subprocess.run(argv,env=desktop_ps.environment() if Path(argv[0]).name.lower()=='powershell.exe' else None,capture_output=True,timeout=90);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr);c.require(run.returncode==0,name+'_failed')
    summary=dict(status='PASS_OFFLINE_F346_INSTALLER',plan=str(path),plan_sha256=digest,tests=39,default_entrypoints_read_only=True,hardware_actions=False,candidate_sha256=images['f340']['sha256'],rollback_sha256=images['f321']['sha256'])
    (out/'result.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='ascii');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
