"""Single passive SPI-control observation, guarded by the actual F340 owner.
Preparation/default CLI are offline. No flash writer or deliberate fault exists.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,secrets,subprocess,time
import f354_protocol as protocol
import f346_install_contract as c
import f346_install_executor as prior
import f346_powershell as desktop_ps
from f336_wdt_ram_executor import Capture,inactive_hardware,Failure,require

MODULE='qtn_topaz_spi_control_probe'
SUPERVISOR='/usr/sbin/om-watchdog-supervisor'
PROBE_SHA='6ec075b4875890d5f366ff568932b591b59cc15231282274d77bb868a768a06a'
SUPERVISOR_SHA='cc6492dc5d5689f30e3c22bdfd843e3bb40c2b19a53ddd6bdd94d3775d05fb9a'
LOADER='/usr/sbin/ram-insmod-qtn'
LOADER_SHA='8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6'
def vocabulary(plan):
    commands={'md.l 0xe0000004 1','md.l 0xf4000000 1','md.l 0xf4000008 1','md.l 0x84000000 1','iminfo 0x83000000','bootm 0x83000000','setenv bootargs '+plan['bootargs'],'printenv bootargs'}
    for item in plan['protected']['parts']:
        commands.add(prior.read_command(item['offset'],item['bytes']));commands.add(prior.crc_command(c.READBACK,item['bytes']))
    for offset,n in [(c.LIVE,c.SLOT),(c.STORE,c.STORE_BYTES)]:commands.add(prior.read_command(offset,n));commands.add(prior.crc_command(c.READBACK,n))
    image=plan['images']['f340'];commands.add(prior.read_command(c.LIVE,image['bytes'],c.LOAD));commands.add(prior.crc_command(c.LOAD,image['bytes']))
    return frozenset(commands)
class Uart(Capture):
    def __init__(self,plan,guard,out):
        super().__init__({'kernel':plan['images']['f340'],'bootargs':plan['bootargs']},guard,out);self.allowed=vocabulary(plan)
class Host(prior.Host):
    def ssh(self,command,data=b'',timeout=20,allow_disconnect=False):
        if not getattr(self,'_capture_probe',False):return super().ssh(command,data,timeout,allow_disconnect)
        require(not allow_disconnect,'probe_disconnect_forbidden');require(self.network_guard(),'network_guard')
        p=subprocess.Popen(self.ssh_argv(command),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.children.append(p)
        timed_out=False;out=b'';err=b''
        try:out,err=p.communicate(data,timeout=timeout)
        except subprocess.TimeoutExpired as expired:
            timed_out=True;out=expired.output or b'';err=expired.stderr or b''
            if p.poll() is None:p.kill()
            try:out,err=p.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                self.probe_ssh_diagnostic=protocol.ssh_diagnostic(out);self.probe_ssh_diagnostic.update(transport_timeout=True,containment_unproven=True,stderr_bytes=len(err))
                (self.out/'probe-ssh-allowlisted.json').write_text(json.dumps(self.probe_ssh_diagnostic,indent=2)+'\n',encoding='ascii')
                raise Failure('ssh_containment_unproven') from None
            require(p.poll() is not None,'ssh_containment_unproven')
        self.probe_ssh_diagnostic=protocol.ssh_diagnostic(out)
        self.probe_ssh_diagnostic.update(transport_exit_code=p.returncode,transport_timeout=timed_out,stderr_bytes=len(err))
        (self.out/'probe-ssh-allowlisted.json').write_text(json.dumps(self.probe_ssh_diagnostic,indent=2)+'\n',encoding='ascii')
        require(len(out)<=65536 and len(err)<=65536,'ssh_output_limit')
        require(not timed_out,'ssh_deadline');require(p.returncode==0 and not err,'ssh_failed')
        return out
    def _guard(self,network):
        for path,digest in self.plan['sources'].items():require(c.sha(path)==digest,'source_drift')
        argv=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/assert_f354_context.ps1')]
        if network:argv.append('-CheckNetwork')
        p=subprocess.run(argv,env=desktop_ps.environment(),capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return p.returncode==0 and p.stdout.strip()==b'PASS_F354_PASSIVE_CONTEXT' and not p.stderr
    def initial_binding(self,identity):return json.loads(os.environ.get('OM_F354_CONTEXT','{}')).get('initial_boot_id')==identity['boot_id']
    def preflight(self):
        cmd=f"[ ! -d /sys/module/{MODULE} ] && [ ! -e /run/openmitrastar/watchdog/owner.lock ] && [ ! -e /run/openmitrastar/watchdog/supervisor.sock ] && sha256sum {SUPERVISOR}"
        answer=self.ssh(cmd).split();require(answer and answer[0].decode()==self.plan['supervisor']['sha256'],'supervisor_hash_or_existing_owner')
        answer=self.ssh(f'[ -f {LOADER} ] && [ -x {LOADER} ] && [ ! -L {LOADER} ] && sha256sum {LOADER}').split()
        require(answer==[LOADER_SHA.encode(),LOADER.encode()],'fixed_loader_identity')
        printk=self.ssh('cat /proc/sys/kernel/printk').split()
        require(len(printk)==4 and all(re.fullmatch(rb'[0-9]{1,2}',v) for v in printk) and 6<int(printk[0])<=15,'console_pr_info_suppressed')
        self.storage_gate()
        result=self.watchdog_inactive();result['console_loglevel']=int(printk[0]);return result
    def stage(self,run_id):
        require(re.fullmatch('[0-9a-f]{32}',run_id),'run_id');self.stage_dir='/run/openmitrastar/f354/'+run_id;self.module_path=self.stage_dir+'/probe.ko'
        command=f"umask 077; [ ! -e {self.stage_dir} ] && mkdir -p {self.stage_dir} && chmod 700 {self.stage_dir} && cat >{self.module_path} && chmod 600 {self.module_path}"
        self.ssh(command,Path(self.plan['probe']['path']).read_bytes())
        answer=self.ssh('sha256sum '+self.module_path).split();require(answer and answer[0].decode()==self.plan['probe']['sha256'],'probe_stage_hash')
    def launch_owner(self,token):
        require(re.fullmatch('[0-9a-f]{32}',token),'guardian_token')
        command=f"umask 077; [ ! -e /run/openmitrastar/watchdog/owner.lock ] && [ ! -e /run/openmitrastar/watchdog/supervisor.sock ] || exit 71; (trap '' HUP; exec {SUPERVISOR} --session {token} 180000) </dev/null >{self.stage_dir}/owner.stdout 2>{self.stage_dir}/owner.stderr & printf 'F354_OWNER_PID=%s\\n' \"$!\""
        text=self.ssh(command);match=re.fullmatch(rb'F354_OWNER_PID=([1-9][0-9]{0,9})\n',text);require(match and int(match[1])<(1<<31),'guardian_launch_pid');return int(match[1])
    def status(self,token):return json.loads(self.ssh(f'{SUPERVISOR} --status {token}',timeout=12))
    def arm_begin(self,token):
        command=f'{SUPERVISOR} --request {token} 1 ARM && {SUPERVISOR} --request {token} 1 BEGIN {protocol.PHASE} 60000'
        rows=self.ssh(command,timeout=12).splitlines();require(len(rows)==2,'arm_begin_response_count');return [json.loads(row) for row in rows]
    def passive_probe(self,boot_id):
        params=' '.join(protocol.PARAMETERS)
        command=f'''PATH=/sbin:/bin:/usr/sbin:/usr/bin
export PATH
[ ! -d /sys/module/{MODULE} ] || exit 71
[ "$(sha256sum {self.module_path} | awk '{{print $1}}')" = {self.plan['probe']['sha256']} ] || exit 72
[ -f {LOADER} ] && [ -x {LOADER} ] && [ ! -L {LOADER} ] && [ "$(sha256sum {LOADER} | awk '{{print $1}}')" = {LOADER_SHA} ] || exit 73
load_rc=0
{LOADER} {self.module_path} 'execute_read=1' >{self.stage_dir}/insmod.stdout 2>{self.stage_dir}/insmod.stderr || load_rc=$?
printf 'load_rc=%s\n' "$load_rc"
case "$(cat {self.stage_dir}/insmod.stdout)" in
 RAM_INSMOD_OK) loader_report=ok;;
 RAM_INSMOD_LOAD_FAIL) loader_report=load_fail;;
 RAM_INSMOD_OPEN_FAIL) loader_report=open_fail;;
 'RAM_INSMOD_USAGE module.ko [parameters]') loader_report=usage;;
 *) loader_report=other;;
esac
loader_stderr_present=0
[ ! -s {self.stage_dir}/insmod.stderr ] || loader_stderr_present=1
printf 'loader_report=%s\nloader_stderr_present=%s\n' "$loader_report" "$loader_stderr_present"
snapshot_rc=1
unload_rc=-1
if [ "$load_rc" -eq 0 ]; then
 snapshot_rc=0
 for field in {params}; do
  value=$(cat /sys/module/{MODULE}/parameters/$field 2>/dev/null) || snapshot_rc=1
  printf '%s=%s\n' "$field" "$value"
 done
 unload_rc=0
 /bin/rmmod {MODULE} >{self.stage_dir}/rmmod.stdout 2>{self.stage_dir}/rmmod.stderr || unload_rc=$?
fi
present=0
[ ! -d /sys/module/{MODULE} ] || present=1
printf 'snapshot_rc=%s\nunload_rc=%s\nmodule_present=%s\nboot_id=' "$snapshot_rc" "$unload_rc" "$present"
cat /proc/sys/kernel/random/boot_id
printf 'complete=1\n'
'''
        self._capture_probe=True
        try:return self.ssh(command,timeout=20)
        finally:self._capture_probe=False
    def cease(self,token):return json.loads(self.ssh(f'{SUPERVISOR} --request {token} 1 CEASE',timeout=12))
    def owner_files_gone(self):
        return self.ssh('[ ! -e /run/openmitrastar/watchdog/owner.lock ] && [ ! -e /run/openmitrastar/watchdog/supervisor.sock ] && printf GONE').strip()==b'GONE'
    def clean_unarmed(self):
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            try:
                if self.owner_files_gone():return True
            except Failure:pass
            time.sleep(.5)
        return False
    def cleanup_stage(self):
        self.ssh('rm -f '+self.module_path+' '+self.stage_dir+'/insmod.stdout '+self.stage_dir+'/insmod.stderr '+self.stage_dir+'/rmmod.stdout '+self.stage_dir+'/rmmod.stderr '+self.stage_dir+'/owner.stdout '+self.stage_dir+'/owner.stderr')

def wait_owner(host,token,boot,pid):
    end=time.monotonic()+15
    while time.monotonic()<end:
        try:
            row=protocol.owner(host.status(token),token,boot,pid);protocol.idle(row);return row
        except (Failure,ValueError):time.sleep(.2)
    raise Failure('guardian_idle_not_verified')
def wait_reset(uart,previous_count,seconds):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        require(not uart.failed,'uart_capture_failed')
        if len(uart.reset_times)>previous_count:
            uart.wait_prompt(60);return True
        time.sleep(.05)
    return False
def wait_probe_uart(uart,start,observation,previous_reset_count):
    # SSH completion does not drain the independent serial reader. Wait only
    # for already-issued printk evidence; never issue or repeat a device action.
    deadline=time.monotonic()+2.0
    while True:
        require(not uart.failed,'uart_capture_failed')
        require(len(uart.reset_times)==previous_reset_count,'reset_instead_of_probe')
        try:
            return protocol.uart(uart.since(start),observation)
        except protocol.ProtocolError as error:
            if str(error)!='probe_uart_sequence_counts':raise
        require(time.monotonic()<deadline,'probe_uart_deadline')
        time.sleep(.02)
def return_f340(uart,host,plan,old_boot,out):
    observed=inactive_hardware(uart);verification_error=None;proof={}
    try:
        proof['protected']=prior.protected(uart,plan);proof['full_slot_crc32']=prior.flash_crc(uart,c.LIVE,c.SLOT,plan['images']['f340']['full_slot_crc32'])
    except Exception as error:verification_error=str(error) if isinstance(error,Failure) else type(error).__name__
    # Even a witness failure may return the original verified prefix read-only.
    identity=prior.boot_written(uart,host,plan,'f340',old_boot,prefix_only=True)
    platform=host.platform('f340',out/'return-platform');watchdog=host.watchdog_inactive();require(host.owner_files_gone(),'old_guardian_state_survived_reset')
    return dict(post_reset_watchdog=observed,readback=proof,readback_error=verification_error,identity=identity,platform=platform,watchdog=watchdog)
def run(plan,out,host_factory=Host,uart_factory=Uart):
    host=host_factory(plan,out);uart=uart_factory(plan,host.guard,out);run_id=secrets.token_hex(16);token=secrets.token_hex(16)
    result=dict(schema='openmitrastar.f354-passive-result/v1',status='FAILED',flash_write_commands=False,radio_actions=False,deliberate_fault=False,probe_requested=False,probe_read_pass=False,arm_attempted=False,reset_observed=False,software_recovery=False)
    baseline=None;owner=None;pid=None;before_reset=0;returned=False;owner_launch_attempted=False;cease_ok=False;return_attempted=False;watchdog_release_verified=False;arm_start=0;guardian_uncertain=False;probe_start=None
    def diagnostic_uart():
        if probe_start is None:return
        try:
            partial=protocol.uart_partial(uart.since(probe_start));result['probe_uart_partial']=partial
            (out/'probe-uart-partial.json').write_text(json.dumps(partial,indent=2)+'\n',encoding='ascii')
        except Exception as error:result['probe_uart_partial_error']=type(error).__name__
    def event(stage):
        result['stage']=stage
        with (out/'events.jsonl').open('a',encoding='ascii') as f:f.write(json.dumps(dict(stage=stage,host_ms=round(time.monotonic()*1000)))+'\n')
    try:
        event('baseline');require(host.guard(),'lease');baseline=host.identity('f340');require(host.initial_binding(baseline),'initial_nonce_boot_mismatch');result['baseline']=baseline;result['initial_watchdog']=host.preflight()
        uart.open();host.stage(run_id);event('guardian-start');owner_launch_attempted=True;pid=host.launch_owner(token)
        owner=wait_owner(host,token,baseline['boot_id'],pid);result['guardian_idle']=owner
        before_reset=len(uart.reset_times);uart.invalidate_prompt();uart.stop_autoboot(120);arm_start=uart.checkpoint();event('guardian-arm');result['arm_attempted']=True
        raw_arm,raw_begin=host.arm_begin(token);arm=protocol.owner(raw_arm,token,baseline['boot_id'],pid,owner);protocol.armed(arm,2)
        begin=protocol.owner(raw_begin,token,baseline['boot_id'],pid,owner);protocol.armed(begin,3);require(begin['session_deadline_monotonic_ms']==arm['session_deadline_monotonic_ms'],'guardian_total_deadline_changed')
        result['guardian_arm']=arm;result['guardian_begin']=begin
        event('single-passive-probe');probe_start=uart.checkpoint();result['probe_requested']=True
        raw_probe=host.passive_probe(baseline['boot_id'])
        result['probe_ssh']=protocol.ssh_diagnostic(raw_probe)
        (out/'probe-ssh-fields.json').write_text(json.dumps(result['probe_ssh'],indent=2)+'\n',encoding='ascii')
        diagnostic_uart()
        observation=protocol.probe(raw_probe,baseline['boot_id'])
        require(len(uart.reset_times)==before_reset,'reset_instead_of_probe')
        result['probe_uart']=wait_probe_uart(uart,probe_start,observation,before_reset);result['probe']=observation;result['probe_read_pass']=True
        evidence=out/'probe-uart-sanitized.log';evidence.write_text('\n'.join(result['probe_uart']['validated_lines'])+'\n',encoding='ascii')
        result['probe_uart_artifact']={'path':str(evidence),'sha256':c.sha(evidence)}
        event('planned-guardian-cease');row=protocol.owner(host.cease(token),token,baseline['boot_id'],pid,owner);protocol.ceased(row);result['guardian_cease']=row;cease_ok=True
        require(wait_reset(uart,before_reset,40),'watchdog_cleanup_reset_missing');result['reset_observed']=True
        require(protocol.FATAL.search(uart.since(arm_start)) is None,'fault_during_probe_epoch')
        result['post_reset_watchdog']=inactive_hardware(uart);watchdog_release_verified=True
        event('readonly-f340-return');return_attempted=True;result['return']=return_f340(uart,host,plan,baseline['boot_id'],out);returned=True
        require(not result['return']['readback_error'],'return_readback_verification_failed')
        result['status']='PASS_F354_PASSIVE_CONTROL_READ_AND_F340_RETURN';event('complete')
    except Exception as error:
        diagnostic_uart()
        if hasattr(host,'probe_ssh_diagnostic'):result['probe_ssh_transport']=host.probe_ssh_diagnostic
        result['error']=str(error) if isinstance(error,(Failure,protocol.ProtocolError)) else type(error).__name__
        if owner_launch_attempted and owner is None and baseline:
            try:
                raw=host.status(token);candidate_pid=raw.get('owner_pid')
                reconciled=protocol.owner(raw,token,baseline['boot_id'],candidate_pid)
                if pid is not None:require(candidate_pid==pid,'launch_pid_reconciliation_mismatch')
                pid=candidate_pid;owner=reconciled;result['guardian_reconciled']=reconciled
                guardian_uncertain=reconciled['fd_held'] or reconciled['hardware_arm_confirmed']
            except Exception:result['guardian_reconciliation_unconfirmed']=True
        if (result['arm_attempted'] or guardian_uncertain) and baseline and not return_attempted:
            try:
                if not uart.has_prompt() and len(uart.reset_times)==before_reset:
                    if not cease_ok:
                        try:
                            row=protocol.owner(host.cease(token),token,baseline['boot_id'],pid,owner);result['recovery_cease']=row
                        except Exception:result['recovery_cease_unconfirmed']=True
                    if cease_ok or not wait_reset(uart,before_reset,80):
                        result['software_recovery']=True;host.reboot_to_prompt(uart,software_recovery=True)
                result['reset_observed']=len(uart.reset_times)>before_reset
                require(uart.has_prompt(),'recovery_bootbase_missing');event('failed-probe-readonly-return')
                result['post_reset_watchdog']=inactive_hardware(uart);watchdog_release_verified=True;return_attempted=True
                result['return']=return_f340(uart,host,plan,baseline['boot_id'],out);returned=True;result['status']='FAIL_PROBE_WITH_F340_RETURN'
            except Exception as recovery:result['recovery_error']=str(recovery) if isinstance(recovery,(Failure,protocol.ProtocolError)) else type(recovery).__name__
        elif owner_launch_attempted and not result['arm_attempted']:
            try:
                result['unarmed_owner_exited']=host.clean_unarmed()
                if result['unarmed_owner_exited']:result['unarmed_cleanup_watchdog']=host.watchdog_inactive()
            except Exception:result['unarmed_owner_exited']=False
            if not result['unarmed_owner_exited']:guardian_uncertain=True
    finally:
        diagnostic_uart()
        # The Linux guardian is detached before ARM. Local SSH cleanup cannot
        # intentionally close its watchdog FD; it is never killed here.
        result['guardian_may_remain_armed']=(result['arm_attempted'] or guardian_uncertain) and not watchdog_release_verified
        result['guardian_cease_confirmed']=cease_ok
        result['return_attempted']=return_attempted;result['baseline_returned']=returned
        if not result['arm_attempted'] and getattr(host,'module_path',None) and (not owner_launch_attempted or result.get('unarmed_owner_exited')):
            try:host.cleanup_stage()
            except Exception:result['stage_cleanup_failed']=True
        try:result['local_helpers_contained']=host.contain()
        except Exception:result['local_helpers_contained']=False
        try:result['uart_capture']=uart.close()
        except Exception:result['uart_capture']={}
        result['containment_confirmed']=result['local_helpers_contained'] and result['uart_capture'].get('reader_stopped') is True and result['uart_capture'].get('port_closed') is True
        result['retain_lease_required']=not result['containment_confirmed'] or result['guardian_may_remain_armed']
        if not result['containment_confirmed'] or result['uart_capture'].get('reader_error'):result['status']='FAIL_CAPTURE_OR_CONTAINMENT'
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))),flush=True);return 0 if result['status']=='PASS_F354_PASSIVE_CONTROL_READ_AND_F340_RETURN' else 1
def load_plan(path,digest):
    require(c.sha(path)==digest,'plan_hash');p=json.loads(Path(path).read_text(encoding='ascii'));require(p['schema']=='openmitrastar.f354-passive-plan/v1' and p['status']=='PASS_OFFLINE_PASSIVE_GATE','plan_scope')
    require(p['images']=={'f340':c.images()['f340']} and p['bootargs']==c.BOOTARGS and p['protected']==c.protected_backups(),'baseline_contract')
    require(p['flash_writes_allowed'] is False and p['radio_tests_allowed'] is False and p['deliberate_fault_allowed'] is False and p['one_shot'] is True,'plan_action_scope')
    require(p['probe']['sha256']==PROBE_SHA and p['probe']['bytes']==7592 and c.sha(p['probe']['path'])==PROBE_SHA and Path(p['probe']['path']).stat().st_size==7592,'probe_hash')
    require(p['supervisor']['sha256']==SUPERVISOR_SHA and p['supervisor']['bytes']==33720 and c.sha(p['supervisor']['path'])==SUPERVISOR_SHA and Path(p['supervisor']['path']).stat().st_size==33720,'supervisor_hash')
    require(p['loader']['sha256']==LOADER_SHA and p['loader']['bytes']==816 and p['loader']['runtime_path']==LOADER and c.sha(p['loader']['path'])==LOADER_SHA,'loader_hash')
    for file,digest in p['sources'].items():require(c.sha(file)==digest,'source_drift')
    return p
def main():
    ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args();p=load_plan(a.plan,a.plan_sha256)
    if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID',hardware_actions=False)));return 0
    require(os.environ.get('OM_F354_CONTEXT') and a.output_dir and a.output_dir.is_dir(),'owning_launcher_required');return run(p,a.output_dir)
if __name__=='__main__':raise SystemExit(main())
