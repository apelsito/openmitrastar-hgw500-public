"""Build test-only guardian and pin passive F349 execution. Never device IO."""
from pathlib import Path
from datetime import datetime,timezone
import json,shlex,shutil,subprocess,sys
import f349_probe_executor as executor
import f346_install_contract as c
import f346_powershell as desktop_ps

def linux(path):
    p=Path(path).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
    out=c.ROOT/'outputs/preflight'/('f349-passive-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    images={'f340':c.images()['f340']};backups=c.protected_backups()
    def proof(relative,digest,status):
        path=c.ROOT/relative;c.require(c.sha(path)==digest,'proof_hash');data=json.loads(path.read_text(encoding='ascii'));c.require(data['status']==status,'proof_status')
        return data,dict(path=str(path),sha256=digest,status=status)
    probe,probeproof=proof('outputs/kernel-port/f347-passive-spi-control-20260921T145647Z/result.json','e2028aa54e32f20074d0034f0da603c45fe46e6ced4fe7e60556487fc41848c3','PASS_OFFLINE_REBUILD_DEVICE_EXECUTION_UNRUN')
    guardian,guardianproof=proof('outputs/kernel-port/f340-supervisor-20260921T133917Z/result.json','9a1cd8aba1d2bf3f733a59252d8f64db50ac6087235f67edc981e90c4e4672a8','PASS_OFFLINE_SUPERVISOR')
    live,liveproof=proof('outputs/handoff-live/f346-install-20260921T151945Z-f4aa6c0b/result.json','6e90829ab30bac2d0ea80f24fa3c7020436be8b192db5991ac22ed1e18376600','PASS_F340_PERSISTENT_WATCHDOG_BASELINE')
    platform,platformproof=proof('outputs/handoff-live/f346-install-20260921T151945Z-f4aa6c0b/platform-f340/status.json','a57665424ac985bdd7e96f86b95b84f4c177b522959e43ae47dbe7baae984ae0','PASS')
    qual,qualproof=proof('outputs/preflight/f340-qualified-20260921T134752Z/result.json','a2c151a6f437e5671c9af56df60376d414290feb10afd2160249e0b9994bf354','PASS_OFFLINE_FULLIMAGE_AND_SUPERVISOR')
    c.require(probe['mmio_scope']==dict(sysctl_map_reads=1,spi_control_reads=1,writes=0,flash_command_apertures=0) and probe['source_changed_from_f320'] is False and probe['deliberate_cpu_fault'] is False,'probe_scope')
    c.require(len(platform['checks'])==27 and all(v is True for v in platform['checks'].values()) and live['watchdog']['ready_for_arm']==1 and live['watchdog']['device_opened']==0 and live['containment_confirmed'] is True,'physical_baseline_proof')
    c.require(probe['artifact']['sha256']==executor.PROBE_SHA and guardian['artifact']['sha256']==executor.SUPERVISOR_SHA,'artifact_identity')
    for artifact in (probe['artifact'],guardian['artifact']):c.require(c.sha(artifact['path'])==artifact['sha256'] and Path(artifact['path']).stat().st_size==artifact['bytes'],'artifact_hash')
    for report in (probe,guardian):
        for name,digest in report['sources'].items():c.require(c.sha(c.ROOT/name)==digest,'upstream_source_drift')
    files={Path(m.__file__).resolve() for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(c.ROOT/'tools')}
    files.update(c.ROOT/'tools'/name for name in ['prepare_f349_passive_probe.py','test_f349_passive.py','test_f349_context.ps1','test_f349_native_owner.py','run_f349_passive_probe.ps1','f349_hardware_context.ps1','assert_f349_context.ps1',
        'f321_mtd4_runtime.ps1','f321_process_job.cs','f321_native_job_launcher.ps1','f319_uart_guard.ps1','f319_recovery_guard.ps1','f321_ssh_guard.ps1','f336_host_network.ps1','post_flash_f214_device_gate.py'])
    files.update(c.ROOT/'work/pydeps/serial'/name for name in ['__init__.py','serialutil.py','serialwin32.py','win32.py'])
    image=images['f340'];files.update([Path(image['path']),Path(image['directory'])/'manifest.json',Path(image['known_hosts_path']),Path(backups['manifest'])]);files.update(Path(p['path']) for p in backups['parts'])
    proofs=[probeproof,guardianproof,liveproof,platformproof,qualproof];files.update(Path(p['path']) for p in proofs)
    for report in (probe,guardian):files.update((c.ROOT/name).resolve() for name in report['sources'])
    files.update(Path(a['path']) for a in (probe['artifact'],guardian['artifact']))
    pins={str(p):c.sha(p) for p in sorted(files)}
    source=c.ROOT/'work/kernel-port/versions/f340-watchdog-supervisor';shutil.copytree(source,out/'guardian-test-source')
    q=shlex.quote
    script=f'''set -eu
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-function -pedantic -DF340_TEST {q(linux(out/'guardian-test-source/f340_supervisor.c'))} -o {q(linux(out/'supervisor-test'))}
python3 {q(linux(c.ROOT/'tools/test_f349_native_owner.py'))} --binary {q(linux(out/'supervisor-test'))} --result {q(linux(out/'native-owner-tests.json'))}
'''
    (out/'test-native.sh').write_bytes(script.encode('ascii'))
    jobs=[([sys.executable,str(c.ROOT/'tools/test_f349_passive.py'),'--result',str(out/'python-tests.json')],'python-tests'),
          ([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f349_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context-tests'),
          (['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'test-native.sh')],'native-owner-tests')]
    for argv,name in jobs:
        run=subprocess.run(argv,env=desktop_ps.environment() if Path(argv[0]).name.lower()=='powershell.exe' else None,capture_output=True,timeout=120)
        (out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr)
        if run.returncode:(out/'result.json').write_text(json.dumps(dict(status='FAILED_OFFLINE_TESTS',test=name,returncode=run.returncode,hardware_actions=False),indent=2)+'\n',encoding='ascii')
        c.require(run.returncode==0,name+'_failed')
    tests={}
    for name,count in [('python',31),('context',17),('native-owner',4)]:
        path=out/(name+'-tests.json');data=json.loads(path.read_text(encoding='ascii'));actual=len(data['cases']) if name=='native-owner' else data['tests'];c.require(data['passed'] is True and actual==count,'test_count')
        tests[name]=dict(path=str(path),sha256=c.sha(path),count=count)
    c.require(all(c.sha(path)==digest for path,digest in pins.items()),'source_changed_during_tests')
    plan=dict(schema='openmitrastar.f349-passive-plan/v1',status='PASS_OFFLINE_PASSIVE_GATE',created_at_utc=datetime.now(timezone.utc).isoformat(),images=images,protected=backups,proofs=proofs,sources=pins,tests=tests,
        probe=probe['artifact'],supervisor=guardian['artifact'],bootargs=c.BOOTARGS,known_hosts=image['known_hosts_path'],uart_pnp_device_id=c.PNP,physical_lock_dir=str(c.ROOT/'outputs/locks/f301-physical-radio.lock'),
        network=dict(server_ipv4='192.168.1.49',client_ipv4='192.168.1.90',interface_index=18,interface_alias='Ethernet',python_executable=sys.executable),
        hardware_actions=False,physical_authorization_claimed_by_plan=False,flash_writes_allowed=False,radio_tests_allowed=False,aelita_access_allowed=False,deliberate_fault_allowed=False,one_shot=True,
        watchdog_policy='Actual F340 peer-verified owner; explicit ARM+BEGIN spi-control-read 60000; no owner kill, close or magic disarm. CEASE followed by reset and direct read-only F340 return.',
        success_policy='Two passive reads, zero SPI writes, module unloaded, no reset/fault before read completion, verified CEASE, observed reset, inactive Bootbase WDT, exact F340/protected CRCs, new F340 boot, 27 platform checks and inactive WDT.',
        failure_policy='Never repeat probe. Preserve FAIL even after successful F340 return. No repeated bootm. Retain host lease barrier if local containment or watchdog release cannot be demonstrated.',
        limits=['This is not F343 and does not deliberately halt a CPU or access an invalid address','A fault/reset before completed read is FAIL, never a recovery qualification','The normal post-CEASE cleanup reset does not prove CPU/bus/full-chip reset behavior','SYSCTL+SPI_CONTROL observation does not identify the flash part or provide transaction ownership','No SPI command apertures, flash write/erase, WPSEL, protection mutations or persistent boot environment','Empty UUID RAM directory may remain after unarmed cleanup; its explicit files are removed only after confirmed owner exit','No live router, serial, LAN, radio or flash action is performed by preparation/default invocation'])
    path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=c.sha(path);executor.load_plan(path,digest)
    for argv,name in [([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/run_f349_passive_probe.ps1'),'-PlanPath',str(path),'-PlanSha256',digest],'default-powershell'),([sys.executable,str(c.ROOT/'tools/f349_probe_executor.py'),'--plan',str(path),'--plan-sha256',digest],'default-python')]:
        run=subprocess.run(argv,env=desktop_ps.environment() if name=='default-powershell' else None,capture_output=True,timeout=90);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr);c.require(run.returncode==0 and not run.stderr,name+'_failed')
    result=dict(status='PASS_OFFLINE_F349_PASSIVE_GATE',plan=str(path),plan_sha256=digest,tests=52,source_pins=len(pins),default_entrypoints_read_only=True,hardware_actions=False,probe_sha256=executor.PROBE_SHA,production_guardian_sha256=executor.SUPERVISOR_SHA)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
