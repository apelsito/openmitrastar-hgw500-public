"""One physical serial BREAK+b test on healthy F361. Default is file-only."""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,time
import f346_install_executor as prior
import f346_powershell as desktop_ps
import f336_wdt_ram_executor as base
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f362-uart-evidence')
VERSION='lyoko-foundation-6.9.9-f361-config-persistence-device'
ACTIVE_SHA='073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9'
Failure,require=base.Failure,base.require
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def native_break(port,enabled):
 from serial import win32
 call=win32.SetCommBreak if enabled else win32.ClearCommBreak
 require(bool(call(port._port_handle)),'break_api_failed')
def break_b(capture,record,linux_confirmed,drive=native_break,sleep=time.sleep,clock=time.monotonic):
 require(linux_confirmed is True and capture.guard() and not capture.failed,'linux_epoch_or_lease')
 require(not capture.autoboot and not re.search(rb'(?:topaz>|ZHAL>)\s*$',capture.tail()),'bootloader_or_intercept_active')
 require(capture.serial.is_open and capture.serial.out_waiting==0,'serial_not_idle')
 before=len(capture.reset_times);start=clock();record.update(break_attempted=True,break_asserted=False,break_cleared=False,b_attempted=False,b_written=False)
 try:
  drive(capture.serial,True);record['break_asserted']=True;sleep(.600)
 finally:
  drive(capture.serial,False);record['break_cleared']=True
 sleep(.150)
 require(clock()-start<4.0 and len(capture.reset_times)==before and not capture.failed,'sysrq_window_or_epoch_changed')
 record['b_attempted']=True;require(capture.serial.write(b'b')==1,'sysrq_short_write');record['b_written']=True;record['send_elapsed_ms']=round((clock()-start)*1000)
class Capture(base.Capture):
 def __init__(self,plan,guard,out):
  super().__init__({'kernel':{'path':'unused','bytes':1},'bootargs':''},guard,out);self.allowed=frozenset()
class Host(prior.Host):
 def _guard(self,network):
  for path,digest in self.plan['sources'].items():require(sha(path)==digest,'source_drift')
  args=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/assert_f362_uart_context.ps1')]
  if network:args.append('-CheckNetwork')
  p=subprocess.run(args,env=desktop_ps.environment(),capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));return p.returncode==0 and p.stdout.strip()==b'PASS_F362_UART_CONTEXT' and not p.stderr
 def snapshot(self):
  script="printf 'boot_id='; cat /proc/sys/kernel/random/boot_id; printf 'uts='; uname -v; printf 'kernel='; uname -r; printf 'version='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release; printf 'ready='; cat /run/openmitrastar/boot-state 2>/dev/null; printf 'source='; sed -n 's/^source=//p' /run/openmitrastar/config-journal/state 2>/dev/null; printf 'sequence='; sed -n 's/^sequence=//p' /run/openmitrastar/config-journal/state 2>/dev/null; printf 'active_sha='; sha256sum /run/openmitrastar/config/active.conf 2>/dev/null | awk '{print $1}'; printf 'sysrq='; cat /proc/sys/kernel/sysrq; printf 'watchdog_control='; cat /sys/class/watchdog/watchdog0/f340_control; printf 'lock_absent='; if [ ! -e /run/openmitrastar/config-journal/lock ] && [ ! -e /run/openmitrastar/watchdog/owner.lock ]; then printf '1\\n'; else printf '0\\n'; fi; printf 'fatal_count='; dmesg | grep -Eic 'Kernel panic|Oops:|BUG:|MuC has halted|EV_TLB|EV_ProtV' || true"
  rows={}
  for line in self.ssh(script).decode('ascii').splitlines():
   require('=' in line,'snapshot_line');key,value=line.split('=',1);require(key not in rows,'snapshot_duplicate');rows[key]=value
  return rows
def valid_snapshot(row):
 require(re.fullmatch('[0-9a-f-]{36}',row.get('boot_id','')),'boot_id')
 require(row.get('uts')=='#358 @1790006400' and row.get('kernel')=='5.10.260-openmitrastar-radiohw' and row.get('version')==VERSION,'kernel_identity')
 require(row.get('ready')=='ready' and row.get('source')=='journal' and row.get('sequence')=='2' and row.get('active_sha')==ACTIVE_SHA,'ready_journal_identity')
 require(row.get('lock_absent')=='1' and row.get('fatal_count')=='0' and re.fullmatch('[0-9a-f]{8}',row.get('watchdog_control','')) and not int(row['watchdog_control'],16)&1,'busy_or_unhealthy')
 require(re.fullmatch('[0-9]+',row.get('sysrq','')),'sysrq_value');mask=int(row['sysrq']);require(mask==1 or bool(mask&128),'sysrq_reboot_disabled');return row
def run(plan,out):
 host=Host(plan,out);capture=Capture(plan,host.guard,out);result=dict(status='FAILED',flash_writes=False,bootbase_commands=False,autoboot_intercept=False,radio_tests=False,sysrq_requests=0);record={};start=None
 try:
  before=valid_snapshot(host.snapshot());context=json.loads(os.environ['OM_F362_UART_CONTEXT']);require(before['boot_id']==context['initial_boot_id'],'nonce_boot_changed');result['before']=before
  capture.open();current=valid_snapshot(host.snapshot());require(current['boot_id']==before['boot_id'],'prebreak_boot_changed');start=capture.checkpoint();reset_count=len(capture.reset_times)
  result['sysrq_requests']=1;break_b(capture,record,True);result['wire']=record
  deadline=time.monotonic()+30
  while len(capture.reset_times)==reset_count and time.monotonic()<deadline:
   require(not capture.failed,'uart_reader_failed');time.sleep(.05)
  require(len(capture.reset_times)>reset_count,'serial_reset_not_seen');result['new_reset_signature']=True
  raw=capture.since(start);result['sysrq_dispatch_seen']=bool(re.search(rb'(?:sysrq\s*:)\s*Resetting',raw,re.I))
  require(result['sysrq_dispatch_seen'],'sysrq_dispatch_not_seen')
  deadline=time.monotonic()+240;after=None
  while time.monotonic()<deadline:
   require(not capture.failed,'uart_reader_failed')
   try:
    row=valid_snapshot(host.snapshot())
    if row['boot_id']!=before['boot_id']:after=row;break
   except (Failure,ValueError,UnicodeError):pass
   time.sleep(3)
  require(after is not None,'new_boot_ready_timeout');result['after']=after;require(not capture.fatal,'uart_fatal_seen');result['status']='PASS_SERIAL_SYSRQ_AND_AUTONOMOUS_F361_RETURN'
 except Exception as error:result['error']=str(error) if isinstance(error,Failure) else type(error).__name__
 finally:
  result['wire']=record
  if record.get('break_attempted') and not record.get('break_cleared') and capture.serial and capture.serial.is_open:
   try:native_break(capture.serial,False);record['break_cleared']=True
   except Exception:record['break_cleanup_failed']=True
  try:result['children_contained']=host.contain()
  except Exception:result['children_contained']=False
  try:result['uart']=capture.close()
  except Exception:result['uart']={}
  result['containment_confirmed']=result['children_contained'] and result['uart'].get('reader_stopped') is True and result['uart'].get('port_closed') is True
  result['retain_lease_required']=not result['containment_confirmed'] or bool(record.get('break_attempted') and not record.get('break_cleared'))
  if result['retain_lease_required'] or result['uart'].get('reader_error'):result['status']='FAIL_CONTAINMENT_OR_UART'
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
 print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))),flush=True);return 0 if result['status'].startswith('PASS_') else 1
def load_plan(path,digest):
 require(sha(path)==digest,'plan_hash');plan=json.loads(Path(path).read_text(encoding='ascii'));require(plan['schema']=='openmitrastar.f362-uart-plan/v1' and plan['status']=='PASS_OFFLINE_UART_PROBE' and plan['flash_writes'] is False and plan['autoboot_intercept'] is False,'plan_scope')
 for file,expected in plan['sources'].items():require(sha(file)==expected,'source_drift')
 return plan
def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args();p=load_plan(a.plan,a.plan_sha256)
 if not a.execute:print('{"status":"OFFLINE_VALID","hardware_actions":false}');return 0
 require(os.environ.get('OM_F362_UART_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==EVIDENCE_ROOT.resolve(),'owning_launcher_required');return run(p,a.output_dir)
if __name__=='__main__':raise SystemExit(main())
