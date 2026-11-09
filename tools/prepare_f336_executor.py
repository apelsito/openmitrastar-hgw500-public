"""Pin the F336 controller and offline evidence. Does not inspect the device."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys
import f336_wdt_ram_executor as runtime
import f336_wdt_ram_contract as c
from f325_existing_permission_contract import validate_permission,PERMISSION,PERMISSION_SHA,PROGRAM

def pin(path):return {'path':str(path.resolve()),'sha256':c.sha(path)}
def main():
    build=c.DEVICE/'analysis/f336-wdt-ram-20260921T123734Z';probe=c.ROOT/'outputs/kernel-port/f336-wdt-probe-20260921T124221Z'
    direct=c.ROOT/'outputs/preflight/f337-direct-f321-return-20260921T130000Z/result.json'
    startup=c.ROOT/'outputs/preflight/f337-f321-startup-writes-20260921T130500Z/result.json'
    c.require(c.sha(direct)=='ae9ccf53191f8297b915b64c4aa1154fd026c0f532d27b621b0e62eb32f4cdaf','direct return evidence drift')
    c.require(c.sha(startup)=='bfb7a077471db5c01c60d4d61e5580f0ddeb3e18fad8e6c0c0bb504fe2cf2156','startup evidence drift')
    b=json.loads((build/'result.json').read_text());p=json.loads((probe/'result.json').read_text());d=json.loads(direct.read_text())
    c.require(b['status']=='PASS_OFFLINE_RAM_ARTIFACT_PHYSICAL_GATES_UNRUN' and p['tests']['passed'],'unqualified binaries')
    evidence=[c.ROOT/'outputs/kernel-port/f336-executor-tests-20260921T133800Z.json',c.ROOT/'outputs/kernel-port/f336-marker-rearm-tests-20260921T133800Z.json',c.ROOT/'outputs/kernel-port/f336-plan-tests-20260921T125300Z-r2.json']
    for e in evidence:c.require(json.loads(e.read_text())['passed'],'offline tests not passed')
    files=[Path(m.__file__).resolve() for name,m in sys.modules.items() if getattr(m,'__file__',None) and (name.startswith(('f325_','f336_')) or name=='dtb_find_nodes')]
    files += [c.ROOT/'tools'/name for name in ['run_f336_wdt_ram.ps1','f336_ram_context.ps1','f336_assert_context.ps1','f336_host_network.ps1','f319_uart_guard.ps1','f321_ssh_guard.ps1','f325_existing_firewall.ps1','test_f336_ram_executor.py','test_f336_marker_and_rearm.py','prepare_f336_executor.py']]
    files += [direct,startup,build/'result.json',probe/'result.json',c.F321/'known_hosts.f321',*evidence]
    sources={str(path):c.sha(path) for path in sorted(set(files))}
    permission=validate_permission(PERMISSION,PERMISSION_SHA,python_executable=PROGRAM)
    plan=dict(schema='openmitrastar.f336-executor/v1',status='REVIEWED_OFFLINE_READY',created_at_utc=datetime.now(timezone.utc).isoformat(),flash_allowed=False,
        kernel=b['artifact'],probe=p['artifact'],sources=sources,bootargs=d['dtb_bootargs'],direct_return=pin(direct),startup_write_audit=pin(startup),
        known_hosts=str(c.F321/'known_hosts.f321'),uart_pnp_device_id=r'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000',
        physical_lock_dir=str(c.ROOT/'outputs/locks/f301-physical-radio.lock'),
        network=dict(firewall_mode='existing-permission',existing_permission=permission,server_ipv4='192.168.1.49',interface_index=18,interface_alias='Ethernet',python_executable=PROGRAM),
        default_mode='inspect',experiment_arm_requires_stdin='ARM',no_automatic_arm=True,firmware_created=False,
        acceptance_limits=['No WDT_PASS from a software fallback or reset after the probe negative verdict','A returning F321 bootm is terminal, never retried','Platform 27-check gate remains a separate required parent step after return','CRC equality binds this attempt, not an old full-slot reference'],
        tests=[pin(e) for e in evidence])
    out=c.ROOT/'outputs/preflight'/('f336-executor-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n');digest=c.sha(path);runtime.load_plan(path,digest)
    summary=dict(status='PASS_OFFLINE_CONTROLLER_AND_PROBE',plan_sha256=digest,controller_tests=sum(json.loads(e.read_text())['tests'] for e in evidence),probe_tests=p['tests']['tests'],
        total_offline_tests=sum(json.loads(e.read_text())['tests'] for e in evidence)+p['tests']['tests'],all_passed=True,hardware_actions_by_builder=False,
        kernel_sha256=b['artifact']['sha256'],kernel_reproducible=b['reproducible'],probe_sha256=p['artifact']['sha256'],watchdog_arm_or_expiry_acceptance=False,
        fixes=['Expected reboot SSH timeout contained; new UART prompt remains mandatory','DT marker read with cat and terminal NUL removed in Python','Autoboot activation records stream floor and ignores prior epochs','Reader failures preserve fixed error code and exception type without raw text'])
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'SHA256SUMS').write_text(digest+'  plan.json\n')
    print(json.dumps({'plan':str(path),'sha256':digest,'status':plan['status'],'hardware_actions':False,'live_execution_unrun':True},indent=2))
if __name__=='__main__':main()
