"""One OBSERVE on installed F358; no RAM kernel boot, TFTP or flash programming."""
from pathlib import Path
import argparse,json,os,re,secrets,subprocess,time
import f356_observe_executor as previous
import f356_protocol as protocol
import f346_install_executor as boot
import f358_install_contract as contract
import f346_powershell as desktop_ps
import f336_wdt_ram_executor as ram

MODULE=previous.MODULE
LOADER=previous.LOADER
LOADER_SHA=previous.LOADER_SHA
SUPERVISOR='/usr/sbin/om-watchdog-supervisor'
SUPERVISOR_SHA='015d16cafef7e13e008fa451dbc25d5887f4e6935e695c2e2cbca90f2ed74904'
CLI='/usr/sbin/om-journal-cli'
PROVIDER='/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn_f356_journal.ko'
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f359-evidence')
Failure,require=ram.Failure,ram.require
save,disk_floor=previous.save,previous.disk_floor
wait_owner,wait_marker=previous.wait_owner,previous.wait_marker
wait_reset=previous.previous.wait_reset
def vocabulary(plan):
 words={'md.l 0xe0000004 1','md.l 0xf4000000 1','md.l 0xf4000008 1','md.l 0x84000000 1','iminfo 0x83000000','bootm 0x83000000','setenv bootargs '+plan['bootargs'],'printenv bootargs'}
 for item in plan['protected']['parts']:
  words.add(boot.read_command(item['offset'],item['bytes']));words.add(boot.crc_command(contract.READBACK,item['bytes']))
 words.add(boot.read_command(contract.LIVE,contract.SLOT));words.add(boot.crc_command(contract.READBACK,contract.SLOT))
 image=plan['images']['f358'];words.add(boot.read_command(contract.LIVE,image['bytes'],contract.LOAD));words.add(boot.crc_command(contract.LOAD,image['bytes']));return frozenset(words)
class Uart(ram.Capture):
 def __init__(self,plan,guard,out):
  super().__init__({'kernel':plan['images']['f358'],'bootargs':plan['bootargs']},guard,out);self.allowed=vocabulary(plan)
class Host(previous.Host):
 def _guard(self,network,transfer=False):
  require(not transfer,'no_tftp_in_f359')
  for path,digest in self.plan['sources'].items():require(contract.sha(path)==digest,'source_drift')
  args=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(contract.ROOT/'tools/assert_f359_context.ps1')]
  if network:args.append('-CheckNetwork')
  result=subprocess.run(args,env=desktop_ps.environment(),capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  return result.returncode==0 and result.stdout.strip()==b'PASS_F359_OBSERVE_CONTEXT' and not result.stderr
 def initial_binding(self,identity):return json.loads(os.environ.get('OM_F359_CONTEXT','{}')).get('initial_boot_id')==identity['boot_id']
 def identity(self,name):
  require(name=='f358','f358_only');row=boot.Host.identity(self,name);require(row['uts']=='#358 @1790006400','kernel_identity');return row
 def preflight(self):
  command=f'[ ! -d /sys/module/{MODULE} ] && [ ! -e /dev/om-f350-journal ] && [ ! -e /run/openmitrastar/watchdog/owner.lock ] && [ ! -e /run/openmitrastar/watchdog/supervisor.sock ] && sha256sum {SUPERVISOR} {LOADER} {CLI} {PROVIDER}'
  rows=self.ssh(command).splitlines();expected=[(SUPERVISOR_SHA,SUPERVISOR),(LOADER_SHA,LOADER),(self.plan['cli']['sha256'],CLI),(self.plan['provider']['sha256'],PROVIDER)]
  require(len(rows)==len(expected) and all(line.split()==[digest.encode(),path.encode()] for line,(digest,path) in zip(rows,expected)),'installed_component_binding');return self.watchdog_inactive()
 def stage(self,run_id):
  require(re.fullmatch('[0-9a-f]{32}',run_id),'run_id');self.stage_dir='/run/openmitrastar/f359/'+run_id;self.supervisor=self.stage_dir+'/supervisor';self.cli=self.stage_dir+'/journal-cli';self.module_path=PROVIDER
  self.ssh(f'umask 077; [ ! -e {self.stage_dir} ] && mkdir -p {self.stage_dir} && chmod 700 {self.stage_dir} && cp {SUPERVISOR} {self.supervisor} && cp {CLI} {self.cli} && chmod 700 {self.supervisor} {self.cli}')
  rows=self.ssh(f'sha256sum {self.supervisor} {self.cli}').splitlines();require(len(rows)==2 and rows[0].split()==[SUPERVISOR_SHA.encode(),self.supervisor.encode()] and rows[1].split()==[self.plan['cli']['sha256'].encode(),self.cli.encode()],'ram_resident_component_hash')
 def inspect_current(self):
  levels=self.ssh('cat /proc/sys/kernel/printk').split();require(len(levels)==4 and all(re.fullmatch(rb'[0-9]{1,2}',v) for v in levels) and 6<int(levels[0])<=15,'console_pr_info_suppressed')
  row=json.loads(self.ssh(self.supervisor+' --inspect'));require(row.get('event')=='inspect' and row.get('ready_for_arm')==1 and row.get('device_opened')==0 and row.get('kernel_profile_verified')==1 and row.get('required_kernel_version')=='#358 @1790006400' and row.get('control_valid')==1 and int(row.get('control','ffffffff'),16)&1==0,'installed_watchdog_profile');return row
 def launch_owner(self,token):
  require(re.fullmatch('[0-9a-f]{32}',token),'owner_token')
  command=f"umask 077; [ ! -e /run/openmitrastar/watchdog/owner.lock ] && [ ! -e /run/openmitrastar/watchdog/supervisor.sock ] || exit 71; (trap '' HUP; exec {self.supervisor} --session {token} 180000) </dev/null >{self.stage_dir}/owner.stdout 2>{self.stage_dir}/owner.stderr & printf 'F359_OWNER_PID=%s\\n' \"$!\""
  answer=self.ssh(command);match=re.fullmatch(rb'F359_OWNER_PID=([1-9][0-9]{0,9})\n',answer);require(match and int(match[1])<(1<<31),'owner_launch_pid');return int(match[1])
def return_f358(uart,host,plan,old_boot,out):
 observed=ram.inactive_hardware(uart);verification_error=None;proof={}
 try:proof['protected']=boot.protected(uart,plan);proof['full_slot_crc32']=boot.flash_crc(uart,contract.LIVE,contract.SLOT,plan['images']['f358']['full_slot_crc32'])
 except Exception as error:verification_error=str(error) if isinstance(error,Failure) else type(error).__name__
 identity=boot.boot_written(uart,host,plan,'f358',old_boot,prefix_only=True);platform=host.platform('f358',out/'return-platform');watchdog=host.watchdog_inactive();require(host.owner_files_gone(),'old_owner_survived_reset')
 return dict(post_reset_watchdog=observed,readback=proof,readback_error=verification_error,identity=identity,platform=platform,watchdog=watchdog)

def run(plan,out,host_factory=Host,uart_factory=Uart):
    disk_floor();host=host_factory(plan,out);uart=uart_factory(plan,host.guard,out);run_id=secrets.token_hex(16);token=secrets.token_hex(16)
    result=dict(schema='openmitrastar.f359-observe-result/v1',status='FAILED',flash_program_commands=False,flash_protection_writes=False,radio_actions=False,provider_load_attempted=False,observe_attempted=False,provider_unload_attempted=False,observe_pass=False,arm_attempted=False,software_recovery=False)
    baseline=None;active_identity=None;owner=None;pid=None;reboot_started=False;owner_launch_attempted=False;return_attempted=False;returned=False;release_verified=True;before_reset=0;op_start=None;observe_start=None;cease_ok=False
    def event(stage,critical=True):
        result['stage']=stage
        try:save(out/'progress.json',dict(stage=stage,monotonic_ms=round(time.monotonic()*1000)))
        except OSError:
            result.setdefault('evidence_write_errors',[]).append(stage)
            if critical:raise Failure('evidence_write_failed') from None
    def diagnostic():
        result['operations']=getattr(host,'operation_diagnostics',{})
        if op_start is not None:
            try:result['uart_observation_epoch']=dict(fatal_seen=protocol.FATAL.search(uart.since(op_start)) is not None,reset_count=len(uart.reset_times)-before_reset,raw_saved=False)
            except Exception:result['uart_observation_epoch']={'unavailable':True}
        if observe_start is not None:
            try:result['observe_uart_partial']=protocol.marker_diagnostic(uart.since(observe_start));save(out/'observe-uart-partial.json',result['observe_uart_partial'])
            except Exception as error:result['observe_uart_partial_error']=type(error).__name__
    try:
        event('baseline');require(host.guard(),'lease');baseline=host.identity('f358');require(host.initial_binding(baseline),'initial_nonce_boot_mismatch');result['baseline']=baseline;result['initial_watchdog']=host.preflight()
        result['platform_before']=host.platform('f358',out/'platform-before');current=host.identity('f358');require(current['boot_id']==baseline['boot_id'],'boot_changed_before_observe');active_identity=baseline
        result['storage']=host.storage_gate();result['devtmpfs']=host.devtmpfs_ready();uart.open();before_reset=len(uart.reset_times);disk_floor();host.stage(run_id);result['watchdog_profile']=host.inspect_current()
        event('owner-start');disk_floor();owner_launch_attempted=True;reboot_started=True;release_verified=False;pid=host.launch_owner(token);owner=wait_owner(host,token,baseline['boot_id'],pid);result['owner_idle']=owner
        before_reset=len(uart.reset_times);uart.invalidate_prompt();uart.stop_autoboot(120);op_start=uart.checkpoint();event('owner-arm');disk_floor();result['arm_attempted']=True
        raw_arm,raw_begin=host.arm_begin(token);arm=protocol.owner(raw_arm,token,active_identity['boot_id'],pid,owner);protocol.armed(arm,2);begin=protocol.owner(raw_begin,token,active_identity['boot_id'],pid,owner);protocol.armed(begin,3)
        require(arm['session_deadline_monotonic_ms']==begin['session_deadline_monotonic_ms'],'owner_deadline_changed');result['owner_arm']=arm;result['owner_begin']=begin
        event('load-readonly-provider');disk_floor();result['provider_load_attempted']=True;result['provider']=protocol.loaded(host.load_provider(),active_identity['boot_id'])
        event('single-observe');disk_floor();observe_start=uart.checkpoint();result['observe_attempted']=True;observation=protocol.observed(host.observe_provider(),plan['expected_spi_control'])
        marker=protocol.marker_verified(wait_marker(uart,observe_start,before_reset),observation)
        require(len(uart.reset_times)==before_reset,'reset_instead_of_observe');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_during_observe');result['observation']=observation;result['observe_uart']=marker;result['observe_pass']=True
        event('unload-after-clean-release');result['provider_unload_attempted']=True;result['unload']=protocol.unloaded(host.unload_provider())
        event('planned-cease');row=protocol.owner(host.cease(token),token,active_identity['boot_id'],pid,owner);protocol.ceased(row);result['owner_cease']=row;cease_ok=True
        require(wait_reset(uart,before_reset,40),'cleanup_reset_missing');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_before_return');result['post_reset_watchdog']=ram.inactive_hardware(uart);release_verified=True
        event('readonly-f358-return');return_attempted=True;result['return']=return_f358(uart,host,plan,active_identity['boot_id'],out);returned=True
        require(not result['return']['readback_error'],'return_readback_failed');result['status']='PASS_F359_READONLY_OBSERVE_AND_F358_RETURN';event('complete')
    except Exception as error:
        result['status']='FAILED';result['error']=str(error) if isinstance(error,(Failure,protocol.ProtocolError)) else type(error).__name__
        if observe_start is not None:
            try:wait_marker(uart,observe_start,before_reset)
            except Exception as marker_error:result['marker_wait_error']=str(marker_error) if isinstance(marker_error,Failure) else type(marker_error).__name__
        diagnostic()
        if owner_launch_attempted and owner is None and active_identity:
            try:
                raw=host.status(token);candidate=raw.get('owner_pid');owner=protocol.owner(raw,token,active_identity['boot_id'],candidate)
                if pid is not None:require(candidate==pid,'owner_pid_reconciliation')
                pid=candidate;result['owner_reconciled']=owner
            except Exception:result['owner_reconciliation_unconfirmed']=True
        if reboot_started and baseline and not return_attempted:
            try:
                require(all(server.close() for server in host.servers),'tftp_not_contained')
                if owner_launch_attempted:
                    if not uart.has_prompt() and len(uart.reset_times)>before_reset:uart.wait_prompt(60)
                    if not uart.has_prompt() and len(uart.reset_times)==before_reset:
                        if result['arm_attempted']:
                            if not cease_ok:
                                try:result['recovery_cease']=protocol.owner(host.cease(token),token,active_identity['boot_id'],pid,owner)
                                except Exception:result['recovery_cease_unconfirmed']=True
                            if cease_ok or not wait_reset(uart,before_reset,80):result['software_recovery']=True;host.reboot_to_prompt(uart,software_recovery=True)
                        else:result['software_recovery']=True;host.reboot_to_prompt(uart,software_recovery=True)
                elif not uart.has_prompt():result['software_recovery']=True;host.reboot_to_prompt(uart,software_recovery=True)
                require(uart.has_prompt(),'fresh_bootbase_missing');result['post_reset_watchdog']=ram.inactive_hardware(uart);release_verified=True
                event('failed-test-readonly-return',critical=False);return_attempted=True;result['return']=return_f358(uart,host,plan,(active_identity or baseline)['boot_id'],out);returned=True;result['status']='FAIL_OBSERVE_WITH_F358_RETURN'
            except Exception as recovery:result['recovery_error']=str(recovery) if isinstance(recovery,(Failure,protocol.ProtocolError)) else type(recovery).__name__
    finally:
        diagnostic();result['baseline_returned']=returned;result['return_attempted']=return_attempted;result['guardian_cease_confirmed']=cease_ok;result['guardian_may_remain_armed']=owner_launch_attempted and not release_verified
        # No failure path unloads the provider or kills a possibly armed owner.
        try:result['local_helpers_contained']=host.contain()
        except Exception:result['local_helpers_contained']=False
        try:result['uart_capture']=uart.close()
        except Exception:result['uart_capture']={}
        result['containment_confirmed']=result['local_helpers_contained'] and result['uart_capture'].get('reader_stopped') is True and result['uart_capture'].get('port_closed') is True
        result['retain_lease_required']=not result['containment_confirmed'] or result['guardian_may_remain_armed']
        if not result['containment_confirmed'] or result['uart_capture'].get('reader_error'):result['status']='FAIL_CAPTURE_OR_CONTAINMENT'
        try:save(out/'result.json',result)
        except OSError:result['status']='FAIL_FINAL_EVIDENCE_WRITE';result['retain_lease_required']=True
    print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))),flush=True);return 0 if result['status']=='PASS_F359_READONLY_OBSERVE_AND_F358_RETURN' else 1

def load_plan(path,digest):
 require(contract.sha(path)==digest,'plan_hash');plan=json.loads(Path(path).read_text(encoding='ascii'));require(plan['schema']=='openmitrastar.f359-observe-plan/v1' and plan['status']=='PASS_OFFLINE_LIVE_OBSERVE_GATE','plan_scope')
 require(plan['images']=={'f358':contract.images()['f358']} and plan['bootargs']==contract.BOOTARGS and plan['protected']==contract.protected_backups(),'image_contract')
 require(plan['allow_program'] is False and plan['observation_commands']==['observe'] and plan['one_shot'] is True and plan['ram_kernel_boot'] is False and plan['tftp_allowed'] is False,'operation_scope')
 require(Path(plan['evidence_root']).resolve()==EVIDENCE_ROOT.resolve(),'evidence_root_scope')
 for key in ('provider','cli','supervisor','loader'):
  item=plan[key];require(contract.sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes'],'component_hash')
 require(plan['supervisor']['sha256']==SUPERVISOR_SHA and plan['provider']['sha256']=='ab88ec603c18cd013f0de1d79eed1ea9c696ca97d2b589e0e8b9aaa8f9251cd4' and plan['loader']['sha256']==LOADER_SHA,'component_profile')
 for file,expected in plan['sources'].items():require(contract.sha(file)==expected,'source_drift')
 return plan
def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');args=ap.parse_args();plan=load_plan(args.plan,args.plan_sha256)
 if not args.execute:print(json.dumps(dict(status='OFFLINE_VALID',hardware_actions=False)));return 0
 require(os.environ.get('OM_F359_CONTEXT') and args.output_dir and args.output_dir.is_dir() and args.output_dir.resolve().parent==EVIDENCE_ROOT.resolve(),'owning_launcher_required');return run(plan,args.output_dir)
if __name__=='__main__':raise SystemExit(main())
