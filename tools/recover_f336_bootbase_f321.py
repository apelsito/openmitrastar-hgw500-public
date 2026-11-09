"""One direct F321 recovery from the completed F336 attempt. No SSH or reboot.
Default creates/validates a file-only plan. Only an owning launcher may execute.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,re,subprocess,sys,time,uuid
import f336_wdt_ram_executor as r
ROOT=Path(__file__).resolve().parents[1]
ORIGIN='f336-ram-20260921T132233Z-03826f49'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def prepare():
    origin=ROOT/'outputs/handoff-live'/ORIGIN;prior=json.loads((origin/'result.json').read_text())
    r.require(prior['status']=='FAILED_UART_CAPTURE' and prior['error']=='ssh_boot_identity_timeout' and prior['containment_confirmed'] is True and prior['trace']['probe_events']==[] and prior['flash_write_commands_issued'] is False,'origin_not_exact')
    old=ROOT/'outputs/preflight/f336-executor-20260921T132136Z/plan.json';base=json.loads(old.read_text())
    observation=ROOT/'outputs/recovery/f336-prompt-observation-20260921T133320Z/result.json';observed=json.loads(observation.read_text())
    r.require(observed['prompt']=='ZHAL' and observed['serial_closed'] is True and observed['lease_released'] is True,'prior_prompt_observation_not_qualified')
    r.require(sha(old)=='b72e99225f904535352a115efd915df6bc1b92fb4ba1b12c6caab703b8c81a8f','origin_plan_changed')
    files=[Path(m.__file__).resolve() for name,m in sys.modules.items() if getattr(m,'__file__',None) and (name.startswith(('f325_','f336_')) or name=='dtb_find_nodes')]
    files += [Path(__file__),ROOT/'tools/recover_f336_bootbase_f321.ps1',ROOT/'tools/assert_f336_bootbase_recovery.ps1',ROOT/'tools/f319_uart_guard.ps1',origin/'result.json',origin/'uart-redacted.jsonl',origin/'root-readonly-marker-probe.json',old,observation]
    plan=dict(schema='openmitrastar.f336-bootbase-recovery/v1',origin_run=ORIGIN,origin_result_sha256=sha(origin/'result.json'),origin_capture_sha256=sha(origin/'uart-redacted.jsonl'),
        sources={str(p.resolve()):sha(p) for p in files},kernel=base['kernel'],bootargs=base['bootargs'],expected_full_crc=prior['flash_crc_before'],
        nonce='OMF336_RECOVERY_'+uuid.uuid4().hex.upper(),python_executable=base['network']['python_executable'],flash_writes_allowed=False,reboot_allowed=False,requires_ssh=False,
        continuity='New exclusive lease and exact FTDI device, bound to the completed prior run; fresh Bootbase nonce required. This does not claim a new SSH nonce or gapless UART between runs.')
    out=ROOT/'outputs/preflight'/('f336-direct-recovery-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False);path=out/'plan.json';path.write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps(dict(plan=str(path),sha256=sha(path),hardware_actions=False),indent=2))
def execute(plan,out):
    children=[]
    def guard():
        for f,h in plan['sources'].items():r.require(sha(f)==h,'recovery_source_drift')
        p=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/assert_f336_bootbase_recovery.ps1')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));children.append(p)
        try:stdout,stderr=p.communicate(timeout=20)
        except subprocess.TimeoutExpired:p.kill();p.communicate(timeout=3);raise r.Failure('recovery_guard_timeout')
        return p.returncode==0 and stdout.strip()==b'PASS_F336_BOOTBASE_RECOVERY_CONTEXT' and not stderr
    uart=r.Capture(plan,guard,out);result=dict(status='FAILED',origin_run=ORIGIN,flash_write_commands_issued=False,reboot_requested=False,fresh_ssh_binding=False,watchdog_arm_requested=False,bootm_attempts=0)
    allowed={'md.l 0xe0000004 1','md.l 0xf4000000 1','md.l 0xf4000008 1','md.l 0x84000000 1','spi_flash read 0x007e0000 0x83000000 0x007a0000','crc32 0x83000000 0x00517000 0x84000000','crc32 0x83000000 0x007a0000 0x84000000','iminfo 0x83000000','setenv bootargs '+plan['bootargs'],'printenv bootargs','bootm 0x83000000','echo '+plan['nonce']}
    uart.allowed=frozenset(allowed)
    try:
        uart.open();time.sleep(.2);uart.stop_autoboot(30);start=uart.checkpoint();uart.invalidate_prompt();r.require(guard(),'lease');r.require(uart.serial.write(b'\r')==1,'prompt_query_short_write');uart.wait_prompt(30,start)
        command='echo '+plan['nonce'];r.require(r.response_lines(uart.command(command),command)==[plan['nonce']],'fresh_bootbase_nonce_missing');result['fresh_bootbase_nonce']=True
        result['watchdog']=r.inactive_hardware(uart);result['full_slot_crc']=f"{r.flash_snapshot(uart,int(plan['expected_full_crc'],16)):08x}"
        r.iminfo(uart);r.environment(uart,'bootargs',plan['bootargs']);result['bootm_attempts']=1;start=uart.command('bootm 0x83000000',handoff=True)
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            r.require(not uart.failed,'uart_reader_failed');tail=uart.since(start)
            if uart.has_prompt():raise r.Failure('direct_bootm_returned_no_retry')
            if re.search(rb'Linux version 5\.10\.260-openmitrastar-radiohw[^\r\n]*#1 @1785024000',tail):result['status']='PASS_F321_KERNEL_BOOT_OBSERVED_UART';break
            time.sleep(.05)
        else:raise r.Failure('f321_boot_banner_timeout')
        result['platform_27_pending']=True
    except Exception as error:result['error']=str(error) if isinstance(error,r.Failure) else type(error).__name__
    finally:
        stopped=True
        for p in children:
            try:
                if p.poll() is None:p.kill()
                p.wait(timeout=3)
            except Exception:stopped=False
        try:result['uart_capture']=uart.close()
        except Exception:stopped=False
        result['containment_confirmed']=stopped and result.get('uart_capture',{}).get('reader_stopped') is True and result.get('uart_capture',{}).get('port_closed') is True
        if not result['containment_confirmed']:result['status']='FAILED_CONTAINMENT'
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))),flush=True);return 0 if result['status']=='PASS_F321_KERNEL_BOOT_OBSERVED_UART' else 1
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path);ap.add_argument('--plan-sha256');ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    if not args.plan:r.require(not args.execute,'plan_required');prepare();return 0
    r.require(sha(args.plan)==args.plan_sha256,'plan_hash');plan=json.loads(args.plan.read_text());r.require(plan['schema']=='openmitrastar.f336-bootbase-recovery/v1' and plan['origin_run']==ORIGIN,'plan_scope')
    for path,h in plan['sources'].items():r.require(sha(path)==h,'source_drift')
    if not args.execute:print(json.dumps(dict(status='OFFLINE_VALID',hardware_actions=False)));return 0
    r.require(os.environ.get('OM_F336_BOOTBASE_RECOVERY') and args.output_dir and args.output_dir.is_dir(),'owning_launcher_required');return execute(plan,args.output_dir)
if __name__=='__main__':raise SystemExit(main())
