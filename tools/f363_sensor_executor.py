"""One F363 sensor activation under the existing watchdog owner; no flash/RF."""
from pathlib import Path
import argparse,json,os,re,secrets,subprocess,time
import f359_observe_executor as previous
import f363_install_executor as installed
import f363_install_contract as c
import f363_sensor_protocol as protocol
import f363_sensor_commands as commands
import f363_thermal_status as thermal
import f346_powershell as desktop_ps
import f336_wdt_ram_executor as ram
Failure,require=ram.Failure,ram.require
save,disk_floor=previous.save,previous.disk_floor
SUPERVISOR,SUPERVISOR_SHA=previous.SUPERVISOR,previous.SUPERVISOR_SHA
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f363-temperature-activation')
class Uart(ram.Capture):
 def __init__(self,plan,guard,out):
  super().__init__({'kernel':plan['images']['f363'],'bootargs':plan['bootargs']},guard,out);self.allowed=frozenset()
class Host(previous.Host):
 def _guard(self,network,transfer=False):
  require(not transfer,'no_temperature_tftp')
  for path,digest in self.plan['sources'].items():require(c.sha(path)==digest,'source_drift')
  args=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/assert_f363_sensor_context.ps1')]
  if network:args.append('-CheckNetwork')
  p=subprocess.run(args,env=desktop_ps.environment(),capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));return p.returncode==0 and p.stdout.strip()==b'PASS_F363_SENSOR_CONTEXT' and not p.stderr
 def initial_binding(self,identity):return json.loads(os.environ.get('OM_F363_SENSOR_CONTEXT','{}')).get('initial_boot_id')==identity['boot_id']
 def identity(self,name='f363'):
  require(name=='f363','thermal_baseline_only');row=installed.Host.identity(self,name);require(row['uts']=='#358 @1790006400','kernel_identity');return row
 def verify_store(self):return installed.Host.verify_store(self)
 def verify_configuration(self):return installed.Host.verify_configuration(self)
 def verify_thermal_disabled(self):return thermal.validate(self.ssh(thermal.command()))
 def preflight(self):
  require(self.owner_files_gone(),'watchdog_owner_exists');self.verify_thermal_disabled()
  path=self.plan['sensor_module']['installed_path'];require(re.fullmatch(r'/lib/modules/[a-zA-Z0-9._/-]+/temp_sens\.ko',path),'sensor_module_path')
  rows=self.ssh('sha256sum '+SUPERVISOR+' '+path).splitlines();require(len(rows)==2 and rows[0].split()==[SUPERVISOR_SHA.encode(),SUPERVISOR.encode()] and rows[1].split()==[self.plan['sensor_module']['sha256'].encode(),path.encode()],'installed_component_hash')
  return self.watchdog_inactive()
 def stage(self,run_id):
  require(re.fullmatch('[0-9a-f]{32}',run_id),'run_id');self.stage_dir='/run/openmitrastar/f363-sensor/'+run_id;self.supervisor=self.stage_dir+'/supervisor'
  self.ssh(f'umask 077; [ ! -e {self.stage_dir} ] && mkdir -p {self.stage_dir} && chmod 700 {self.stage_dir} && cp {SUPERVISOR} {self.supervisor} && chmod 700 {self.supervisor}')
  require(self.ssh('sha256sum '+self.supervisor).split()==[SUPERVISOR_SHA.encode(),self.supervisor.encode()],'ram_owner_hash')
 def find_node(self):
  raw=self.ssh('for d in /sys/class/hwmon/hwmon*; do [ -r "$d/name" ] || continue; [ "$(cat "$d/name")" = topaz_internal ] || continue; printf "%s\\n" "${d##*/}"; done').decode('ascii')
  require(re.fullmatch(r'hwmon[0-9]{1,3}\n',raw),'unique_sensor_node');return raw.strip()
 def arm_begin(self,token):
  rows=self.ssh(f'{self.supervisor} --request {token} 1 ARM && {self.supervisor} --request {token} 1 BEGIN {protocol.PHASE} 60000',timeout=12).splitlines();require(len(rows)==2,'arm_begin_count');return [json.loads(row) for row in rows]
 def activate(self,node):return self.ssh(commands.activation(node,self.stage_dir),timeout=12)
 def sample(self,node):return self.ssh(commands.sample(node,self.stage_dir),timeout=12)
 def autonomous_software_reboot(self):return self.ssh('echo b >/proc/sysrq-trigger',timeout=12,allow_disconnect=True)
 def cleanup_unarmed_stage(self):
  if hasattr(self,'stage_dir'):
   require(re.fullmatch(r'/run/openmitrastar/f363-sensor/[0-9a-f]{32}',self.stage_dir),'stage_cleanup_path')
   self.ssh(f'rm -f {self.stage_dir}/supervisor {self.stage_dir}/activation.stderr {self.stage_dir}/sample.stderr {self.stage_dir}/interval.stderr')
def wait_owner(host,token,boot,pid):
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  try:row=protocol.owner(host.status(token),token,boot,pid);protocol.idle(row);return row
  except (Failure,ValueError):time.sleep(.2)
 raise Failure('owner_idle_unverified')
def wait_reset(uart,count,seconds):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  require(not uart.failed,'uart_capture_failed')
  if len(uart.reset_times)>count:return True
  time.sleep(.05)
 return False
def wait_identity(host,uart,old_boot,seconds=240):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  require(not uart.failed,'uart_capture_failed')
  try:
   row=host.identity()
   if row['boot_id']!=old_boot:return row
  except (Failure,ValueError):pass
  time.sleep(2)
 raise Failure('autonomous_f363_return_timeout')
def run(plan,out,host_factory=Host,uart_factory=Uart):
 disk_floor();host=host_factory(plan,out);uart=uart_factory(plan,host.guard,out);token=secrets.token_hex(16);run_id=secrets.token_hex(16)
 result=dict(schema='openmitrastar.f363-temperature-activation-result/v1',status='FAILED',activation_attempts=0,samples=[],flash_writes=False,radio_actions=False,bootbase_commands=False,autoboot_intercept=False,arm_attempted=False,software_recovery=False)
 baseline=None;owner=None;pid=None;launch_attempted=False;released=True;returned=False;sample_pass=False;start=None;reset_count=0;cease_attempted=False
 def event(stage):
  result['stage']=stage
  try:save(out/'progress.json',dict(stage=stage))
  except OSError:result.setdefault('evidence_write_errors',[]).append(stage)
 try:
  event('baseline');require(host.guard(),'lease');baseline=host.identity();require(host.initial_binding(baseline),'nonce_boot_changed');result['baseline']=baseline;result['watchdog_before']=host.preflight();result['configuration_before']=host.verify_configuration();result['store_before']=host.verify_store()
  result['platform_before']=host.platform('f363',out/'platform-before');require(host.identity()['boot_id']==baseline['boot_id'],'boot_changed_before_activation')
  node=host.find_node();uart.open();reset_count=len(uart.reset_times);start=uart.checkpoint();host.stage(run_id);result['owner_profile']=host.inspect_current();disk_floor()
  event('owner-launch');launch_attempted=True;released=False;pid=host.launch_owner(token);owner=wait_owner(host,token,baseline['boot_id'],pid);result['owner_idle']=owner
  event('owner-arm');result['arm_attempted']=True;raw_arm,raw_begin=host.arm_begin(token);arm=protocol.owner(raw_arm,token,baseline['boot_id'],pid,owner);protocol.armed(arm,2);begin=protocol.owner(raw_begin,token,baseline['boot_id'],pid,owner);protocol.armed(begin,3);require(arm['session_deadline_monotonic_ms']==begin['session_deadline_monotonic_ms'],'owner_deadline_changed');result['owner_arm']=arm;result['owner_begin']=begin
  event('single-sensor-activation');require(len(uart.reset_times)==reset_count and not uart.failed,'reset_before_activation');result['activation_attempts']=1;raw=host.activate(node);result['activation_response']=commands.diagnostic(raw);result['activation']=commands.activated(raw)
  for index in range(3):
   require(len(uart.reset_times)==reset_count and not uart.failed,'reset_during_samples');event('sample-'+str(index+1));raw=host.sample(node);result['last_sample_response']=commands.diagnostic(raw);result['samples'].append(commands.sampled(raw));time.sleep(1)
  require(not uart.fatal and len(uart.reset_times)==reset_count,'fault_during_sensor_read');sample_pass=True
 except Exception as error:result['error']=str(error) if isinstance(error,(Failure,protocol.ProtocolError)) else type(error).__name__
 finally:
  if launch_attempted and baseline:
   try:
    if owner is None:
     raw=host.status(token);candidate=raw.get('owner_pid');owner=protocol.owner(raw,token,baseline['boot_id'],candidate);require(pid is None or candidate==pid,'owner_pid_reconciliation');pid=candidate;result['owner_reconciled']=owner
   except Exception:result['owner_reconciliation_unconfirmed']=True
   try:
    event('cease-and-autonomous-return')
    if result['arm_attempted'] and len(uart.reset_times)==reset_count:
     cease_attempted=True
     try:row=protocol.owner(host.cease(token),token,baseline['boot_id'],pid,owner);protocol.ceased(row);result['owner_cease']=row
     except Exception:result['cease_unconfirmed']=True
     if not wait_reset(uart,reset_count,85):result['software_recovery']=True;host.autonomous_software_reboot();require(wait_reset(uart,reset_count,30),'reset_not_seen')
    elif not result['arm_attempted'] and len(uart.reset_times)==reset_count:
     result['software_recovery']=True;host.autonomous_software_reboot();require(wait_reset(uart,reset_count,30),'reset_not_seen')
    result['return_identity']=wait_identity(host,uart,baseline['boot_id']);result['watchdog_after']=host.watchdog_inactive();require(host.owner_files_gone(),'owner_survived_reset');released=True;returned=True
    result['thermal_after']=host.verify_thermal_disabled();result['configuration_after']=host.verify_configuration();result['store_after']=host.verify_store();result['platform_after']=host.platform('f363',out/'platform-after')
    require(not uart.fatal,'uart_fatal_during_trial')
    result['status']='PASS_F363_SENSOR_SAMPLES_AND_AUTONOMOUS_RETURN' if sample_pass and not result['software_recovery'] and 'owner_cease' in result else 'FAIL_SENSOR_WITH_F363_RETURN'
   except Exception as error:result['recovery_error']=str(error) if isinstance(error,(Failure,protocol.ProtocolError)) else type(error).__name__
  elif not launch_attempted:
   try:host.cleanup_unarmed_stage()
   except Exception:result['stage_cleanup_unconfirmed']=True
  result.update(owner_launch_attempted=launch_attempted,cease_attempted=cease_attempted,baseline_returned=returned,guardian_may_remain_armed=launch_attempted and not released)
  if start is not None:
   try:result['uart_epoch']=dict(reset_signatures=len(uart.reset_times)-reset_count,fatal_seen=bool(uart.fatal),bytes=len(uart.since(start)))
   except Exception:result['uart_epoch_unavailable']=True
  try:result['children_contained']=host.contain()
  except Exception:result['children_contained']=False
  try:result['uart']=uart.close()
  except Exception:result['uart']={}
  result['containment_confirmed']=result['children_contained'] and result['uart'].get('reader_stopped') is True and result['uart'].get('port_closed') is True
  result['retain_lease_required']=not result['containment_confirmed'] or result['guardian_may_remain_armed']
  if not result['containment_confirmed'] or result['uart'].get('reader_error'):result['status']='FAIL_CAPTURE_OR_CONTAINMENT'
  try:save(out/'result.json',result)
  except OSError:result['status']='FAIL_FINAL_EVIDENCE_WRITE';result['retain_lease_required']=True
 print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))));return 0 if result['status']=='PASS_F363_SENSOR_SAMPLES_AND_AUTONOMOUS_RETURN' else 1
def load_plan(path,digest):
 require(c.sha(path)==digest,'plan_hash');plan=json.loads(Path(path).read_text(encoding='ascii'));require(plan['schema']=='openmitrastar.f363-sensor-plan/v1' and plan['status']=='PASS_OFFLINE_SENSOR_ACTIVATION','plan_scope')
 require(plan['images']=={'f363':c.images()['f363']} and plan['store']==c.store_binding() and plan['activation_attempts']==1 and plan['sample_pairs']==3 and not plan['flash_writes'] and not plan['autoboot_intercept'],'operation_scope')
 require(Path(plan['evidence_root']).resolve()==EVIDENCE_ROOT.resolve() and plan['supervisor']['sha256']==SUPERVISOR_SHA,'profile_scope')
 for file,digest in plan['sources'].items():require(c.sha(file)==digest,'source_drift')
 return plan
def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args();p=load_plan(a.plan,a.plan_sha256)
 if not a.execute:print('{"status":"OFFLINE_VALID","hardware_actions":false}');return 0
 require(os.environ.get('OM_F363_SENSOR_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==EVIDENCE_ROOT.resolve(),'owning_launcher_required');return run(p,a.output_dir)
if __name__=='__main__':raise SystemExit(main())
