"""Pin F356 RAM OBSERVE, validate local evidence storage, run offline tests only."""
from pathlib import Path
from datetime import datetime,timezone
import json,shlex,shutil,subprocess,sys
import f356_observe_executor as executor
import f346_install_contract as c
import f346_powershell as desktop_ps
from f325_existing_permission_contract import validate_permission,PERMISSION,PERMISSION_SHA,PROGRAM
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict

BUNDLE=c.ROOT/'outputs/kernel-port/f356-observe-ram-20260921T171309Z/result.json'
BUNDLE_SHA='5ae7ad32f718da536787cb1008450a24ce4551861245ca3c64a5ebcf89fe7d0f'
QUAL=c.ROOT/'outputs/preflight/f356-artifacts-qualified-20260921T171418Z/result.json'
QUAL_SHA='18dfc4ff9f52c83fe6df89534630df535300ddc7f72645509523b08a2057c292'
def linux(path):p=Path(path).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
    executor.disk_floor();c.require(c.sha(BUNDLE)==BUNDLE_SHA and c.sha(QUAL)==QUAL_SHA,'component_bundle_drift')
    bundle=json.loads(BUNDLE.read_text(encoding='ascii'));qual=json.loads(QUAL.read_text(encoding='ascii'))
    c.require(bundle['status']=='PASS_OFFLINE_RAM_OBSERVE_BUNDLE' and bundle['allowed_operation']=='OBSERVE_ONLY' and bundle['allow_program'] is False and bundle['firmware_flash_image'] is False,'bundle_scope')
    c.require(qual['status']=='PASS_OFFLINE_F356_OBSERVE_ARTIFACTS' and len(qual['checks'])==43 and all(v['passed'] is True for v in qual['checks']) and qual['bundle_manifest']['sha256']==BUNDLE_SHA,'component_qualification')
    images={'f340':c.images()['f340']};protected=c.protected_backups();bootargs=bundle['bootargs'];c.require(bootargs==c.BOOTARGS,'bootargs_drift')
    artifacts={key:dict(bundle[key]) for key in ['kernel','provider','supervisor_ram','cli','loader']};artifacts['loader']['runtime_path']=executor.LOADER
    c.require(artifacts['provider']['sha256']=='ab88ec603c18cd013f0de1d79eed1ea9c696ca97d2b589e0e8b9aaa8f9251cd4' and artifacts['provider']['parameters']=='allow_hw=1 allow_program=0','old_or_wrong_provider')
    sourcefiles=set()
    for item in [*artifacts.values(),bundle['rootfs'],bundle['uimage'],bundle['bootbase_contract'],*bundle['exact_kernel_inputs'].values()]:
        path=(c.ROOT/item['path']).resolve();c.require(c.sha(path)==item['sha256'] and path.stat().st_size==item['bytes'],'component_bytes');sourcefiles.add(path)
    cfg=Path(bundle['exact_kernel_inputs']['config']['path']).read_text(encoding='ascii').splitlines()
    c.require('CONFIG_DEVTMPFS=y' in cfg and 'CONFIG_DEVTMPFS_MOUNT=y' in cfg,'misc_devtmpfs_config')
    c.require(Path(bundle['rootfs']['path']).read_bytes()==Path(images['f340']['path']).read_bytes()[0x180000:],'persistent_rootfs_binding')
    contract=image_to_dict(validate_bootbase_slot('F356-RAM',Path(artifacts['kernel']['path']).read_bytes(),0x1000000))
    c.require(contract['accepted_by_contract'] and contract['header']['load']=='0x8493a000' and contract['header']['entry']=='0x8493e000' and contract['header']['lzma_decompressed_sha256']==bundle['exact_kernel_inputs']['raw']['sha256'],'ram_bootbase_contract')
    reports={}
    for name,item in bundle['evidence'].items():
        path=(c.ROOT/item['path']).resolve();c.require(c.sha(path)==item['sha256'],'bundle_evidence_drift');sourcefiles.add(path);reports[name]=json.loads(path.read_text(encoding='ascii'))
    c.require(reports['passive_control']['status']=='PASS_F354_PASSIVE_READ_AND_F340_RETURN' and reports['passive_control']['observed_spi_control']=='00000004','passive_control_required')
    for report in [bundle,reports['provider'],reports['provider_tests'],reports['supervisor']]:
        for name,digest in report['sources'].items():path=(c.ROOT/name).resolve();c.require(c.sha(path)==digest,'component_source_drift');sourcefiles.add(path)
    sourcefiles.add(Path(qual['qualifier']['path']));c.require(c.sha(qual['qualifier']['path'])==qual['qualifier']['sha256'],'qualifier_drift')
    evidence_root=executor.EVIDENCE_ROOT;executor.disk_floor();evidence_root.mkdir(parents=True,exist_ok=True)
    for path in (evidence_root,*evidence_root.parents):c.require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'evidence_root_reparse')
    c.require(evidence_root.resolve()==Path('/workspace/OpenMitraStar/f356-evidence').resolve(),'evidence_root_path')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=c.ROOT/'outputs/preflight'/('f356-observe-'+stamp);out.mkdir(exist_ok=False)
    probe=evidence_root/('prepare-write-probe-'+stamp+'.txt');payload=b'F356_EVIDENCE_LOCAL_WRITE_READBACK\n'
    with probe.open('xb') as stream:c.require(stream.write(payload)==len(payload),'evidence_probe_write')
    c.require(probe.read_bytes()==payload,'evidence_probe_readback');probe.unlink()
    evidence_check=dict(path=str(evidence_root.resolve()),drive='D:',no_reparse_points=True,write_readback_pass=True,C_free=shutil.disk_usage('C:/').free,D_free=shutil.disk_usage('D:/').free,admission_floor_bytes=500*1024*1024,recovery_not_blocked_by_admission_floor=True)
    executor.save(out/'evidence-root.json',evidence_check)
    files={Path(m.__file__).resolve() for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(c.ROOT/'tools')};files.update(sourcefiles)
    files.update(c.ROOT/'tools'/name for name in ['prepare_f356_observe.py','test_f356_observe.py','test_f356_context.ps1','test_f356_native_owner.py','run_f356_observe.ps1','f356_hardware_context.ps1','assert_f356_context.ps1','f321_mtd4_runtime.ps1','f321_process_job.cs','f321_native_job_launcher.ps1','f319_uart_guard.ps1','f319_recovery_guard.ps1','f321_ssh_guard.ps1','f325_existing_firewall.ps1','f336_host_network.ps1','post_flash_f214_device_gate.py'])
    files.update(c.ROOT/'work/pydeps/serial'/name for name in ['__init__.py','serialutil.py','serialwin32.py','win32.py'])
    files.update([BUNDLE,QUAL,Path(protected['manifest']),Path(images['f340']['path']),Path(images['f340']['directory'])/'manifest.json',Path(images['f340']['known_hosts_path']),PERMISSION,out/'evidence-root.json'])
    files.update(Path(item['path']) for item in protected['parts']);pins={str(path):c.sha(path) for path in sorted(files)}
    native=out/'supervisor-test-source';native.mkdir()
    for name in ['f356_supervisor.c','f356_wdt_support.inc','f340_policy.h']:shutil.copyfile(c.ROOT/'work/kernel-port/versions/f356-observe-ram/supervisor'/name,native/name)
    q=shlex.quote;script=f'''set -eu
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-function -pedantic -DF340_TEST {q(linux(native/'f356_supervisor.c'))} -o {q(linux(out/'supervisor-test'))}
python3 {q(linux(c.ROOT/'tools/test_f356_native_owner.py'))} --binary {q(linux(out/'supervisor-test'))} --result {q(linux(out/'native-owner-tests.json'))}
'''
    (out/'native-tests.sh').write_bytes(script.encode('ascii'))
    jobs=[([sys.executable,str(c.ROOT/'tools/test_f356_observe.py'),'--result',str(out/'python-tests.json')],'python-tests'),([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/test_f356_context.ps1'),'-ResultPath',str(out/'context-tests.json')],'context-tests'),(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'native-tests.sh')],'native-owner-tests')]
    for args,name in jobs:
        executor.disk_floor();run=subprocess.run(args,env=desktop_ps.environment() if Path(args[0]).name.lower()=='powershell.exe' else None,capture_output=True,timeout=180)
        (out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr)
        if run.returncode:executor.save(out/'result.json',dict(status='FAILED_OFFLINE_TESTS',test=name,returncode=run.returncode,hardware_actions=False))
        c.require(run.returncode==0,name+'_failed')
    tests={}
    for name,count in [('python',37),('context',24),('native-owner',4)]:
        path=out/(name+'-tests.json');report=json.loads(path.read_text(encoding='ascii'));actual=len(report['cases']) if name=='native-owner' else report['tests'];c.require(report['passed'] is True and actual==count,'test_count')
        tests[name]=dict(path=str(path),sha256=c.sha(path),count=count)
    c.require(all(c.sha(path)==digest for path,digest in pins.items()),'sources_changed_during_tests')
    permission=validate_permission(PERMISSION,PERMISSION_SHA,python_executable=PROGRAM)
    plan=dict(schema='openmitrastar.f356-observe-plan/v1',status='PASS_OFFLINE_OBSERVE_GATE',created_at_utc=datetime.now(timezone.utc).isoformat(),sources=pins,tests=tests,images=images,protected=protected,bootargs=bootargs,**artifacts,
        bundle=dict(path=str(BUNDLE),sha256=BUNDLE_SHA),artifact_qualification=dict(path=str(QUAL),sha256=QUAL_SHA,checks=43),evidence_root=str(evidence_root.resolve()),evidence_root_check=dict(path=str(out/'evidence-root.json'),sha256=c.sha(out/'evidence-root.json')),
        expected_spi_control=4,observation_commands=['observe'],allow_program=False,one_shot=True,hardware_actions=False,firmware_flash_image=False,flash_program_commands_allowed=False,radio_tests_allowed=False,aelita_access_allowed=False,deliberate_fault_allowed=False,
        known_hosts=images['f340']['known_hosts_path'],uart_pnp_device_id=c.PNP,physical_lock_dir=str(c.ROOT/'outputs/locks/f301-physical-radio.lock'),
        network=dict(firewall_mode='existing-permission',existing_permission=permission,server_ipv4='192.168.1.49',client_ipv4='192.168.1.90',interface_index=18,interface_alias='Ethernet',python_executable=PROGRAM),
        readiness='Read-only 27-check platform gate with F340 rootfs/release, followed by exact #350 UTS and unchanged RAM boot ID; devtmpfs rw, storage RO, printk>6 and profile-specific inactive watchdog required before ARM.',
        success_policy='One valid CLI OBSERVE plus one matching post-release UART marker with valid=0f claimed=0 quarantined=0; unload once, verified CEASE/reset, exact read-only F340 return, platform27 and inactive watchdog.',
        failure_policy='Any failed/partial/unknown observation: never unload, never retry; CEASE/reset and one read-only F340 return. Preserve original failure and cache validity mask. Low disk blocks admission only; small recovery/final evidence goes to fixed D root.',
        limits=['No PP02, D8, WREN/WRDI or protection writes with allow_program=0','OBSERVE does temporarily write SPI_CONTROL and trigger SCUR only after IDc22018; this is not the zero-MMIO-write F354 probe','IDc22018 does not identify 35F versus36E','No CPU/bus/full-chip watchdog recovery claim','F350 kernel/DT/config and persistent F340 rootfs remain exact; only RAM kernel selection changes','The physical executor is not run by preparation or default entrypoints'])
    path=out/'plan.json';executor.save(path,plan);digest=c.sha(path);executor.load_plan(path,digest)
    for args,name in [([desktop_ps.executable(),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/run_f356_observe.ps1'),'-PlanPath',str(path),'-PlanSha256',digest],'default-powershell'),([sys.executable,str(c.ROOT/'tools/f356_observe_executor.py'),'--plan',str(path),'--plan-sha256',digest],'default-python')]:
        run=subprocess.run(args,env=desktop_ps.environment() if name=='default-powershell' else None,capture_output=True,timeout=90);(out/(name+'.stdout')).write_bytes(run.stdout);(out/(name+'.stderr')).write_bytes(run.stderr);c.require(run.returncode==0 and not run.stderr,name+'_failed')
    summary=dict(status='PASS_OFFLINE_F356_OBSERVE_EXECUTOR',plan=str(path),plan_sha256=digest,tests=sum(item['count'] for item in tests.values()),source_pins=len(pins),artifact_checks=43,evidence_root=str(evidence_root.resolve()),hardware_actions=False,default_entrypoints_read_only=True)
    executor.save(out/'result.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
