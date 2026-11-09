"""Minimal offline binding for a single serial reboot of current F361."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,sys
import f362_uart_reboot_probe as x
import f346_powershell as ps
import f358_install_contract as c
def main():
 root=c.ROOT;folder=c.DEVICE/'f361-f358-config-persistence-device-bound';base='openmitrastar-linux510-f361-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH';config=folder/(base+'.config')
 text=config.read_text(encoding='ascii').splitlines()
 for line in ['CONFIG_MAGIC_SYSRQ=y','CONFIG_MAGIC_SYSRQ_SERIAL=y','CONFIG_MAGIC_SYSRQ_DEFAULT_ENABLE=0x1','CONFIG_MAGIC_SYSRQ_SERIAL_SEQUENCE=""','CONFIG_SERIAL_8250_CONSOLE=y']:c.require(line in text,'kernel_sysrq_config')
 physical=root/'outputs/handoff-live/f361-autoboot-20260921T194036Z/result.json';r=json.loads(physical.read_text(encoding='ascii'));c.require(r['status']=='PASS_AUTONOMOUS_REBOOT_WITH_SAVED_CONFIG' and r['observed']['sequence']=='2','baseline_autoboot_proof')
 files={Path(m.__file__).resolve() for m in sys.modules.values() if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(root/'tools')}
 files.update(root/'tools'/name for name in ['prepare_f362_uart_probe.py','test_f362_uart_probe.py','run_f362_uart_probe.py','run_f362_uart_probe.ps1','assert_f362_uart_context.ps1','uart_sysrq_reboot.ps1','f321_mtd4_runtime.ps1','f321_process_job.cs','f321_native_job_launcher.ps1','f319_uart_guard.ps1','f319_recovery_guard.ps1','f321_ssh_guard.ps1','f336_host_network.ps1'])
 files.update(root/'work/pydeps/serial'/name for name in ['__init__.py','serialutil.py','serialwin32.py','win32.py']);files.update([config,physical,folder/'manifest.json',folder/'known_hosts.f361'])
 pins={str(path):x.sha(path) for path in sorted(files)};x.EVIDENCE_ROOT.mkdir(parents=True,exist_ok=True)
 out=root/'outputs/preflight'/('f362-uart-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
 run=subprocess.run([sys.executable,str(root/'tools/test_f362_uart_probe.py'),'--result',str(out/'tests.json')],capture_output=True,timeout=60);(out/'tests.stdout').write_bytes(run.stdout);(out/'tests.stderr').write_bytes(run.stderr);c.require(run.returncode==0,'targeted_tests')
 tests=json.loads((out/'tests.json').read_text(encoding='ascii'));c.require(tests['passed'] and tests['tests']==3,'targeted_count');c.require(all(x.sha(path)==digest for path,digest in pins.items()),'source_drift')
 plan=dict(schema='openmitrastar.f362-uart-plan/v1',status='PASS_OFFLINE_UART_PROBE',version=x.VERSION,known_hosts=str(folder/'known_hosts.f361'),sources=pins,tests=dict(path=str(out/'tests.json'),sha256=x.sha(out/'tests.json'),count=3),
  evidence_root=str(x.EVIDENCE_ROOT),uart_pnp_device_id=c.PNP,physical_lock_dir=str(root/'outputs/locks/f301-physical-radio.lock'),network=dict(server_ipv4='192.168.1.49',client_ipv4='192.168.1.90',interface_index=18,interface_alias='Ethernet',python_executable=sys.executable),
  flash_writes=False,autoboot_intercept=False,bootbase_commands=False,break_ms=600,gap_ms=150,transmit_hex='62',requests=1,hardware_actions=False,
  success='Fresh serial SysRq Resetting and reset signature, then new F361 boot ready/journal seq2/active hash preserved, no Bootbase input.',limits=['Requires responsive Linux serial IRQ path; does not prove recovery from a hard CPU/bus lock','No SSH reboot fallback, DTR/RTS pulse, environment write or repeated BREAK/b'])
 path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii');digest=x.sha(path);x.load_plan(path,digest)
 for args,name in [([sys.executable,str(root/'run_f362_uart_probe.py')],'unused')]:pass
 args=[sys.executable,str(root/'tools/run_f362_uart_probe.py'),'--plan',str(path),'--plan-sha256',digest];run=subprocess.run(args,capture_output=True,timeout=60);(out/'default.stdout').write_bytes(run.stdout);(out/'default.stderr').write_bytes(run.stderr);c.require(run.returncode==0 and not run.stderr,'default_readonly')
 result=dict(status='PASS_OFFLINE_F362_UART_REBOOT_PROBE',plan=str(path),plan_sha256=digest,tests=3,source_pins=len(pins),hardware_actions=False);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
