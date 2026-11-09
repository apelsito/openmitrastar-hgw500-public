"""F356 RAM kernel + one identification/status/security observation. No flash writer."""
from pathlib import Path
import argparse,json,os,re,secrets,shutil,subprocess,time
import f356_protocol as protocol
import f354_probe_executor as previous
import f346_install_executor as boot
import f346_install_contract as contract
import f346_powershell as desktop_ps
import f336_wdt_ram_executor as ram
from f325_scoped_tftp import load_verified_file
from f325_ethernet_server_process import ScopedTftpProcess
from f325_ethernet_ram_gate import verify_transfer

MODULE='qtn_f356_journal'
LOADER='/usr/sbin/ram-insmod-qtn'
LOADER_SHA='8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6'
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f356-evidence')
Failure=ram.Failure
require=ram.require
def disk_floor():
    require(shutil.disk_usage('C:/').free>500*1024*1024 and shutil.disk_usage('D:/').free>500*1024*1024,'evidence_disk_floor')
def save(path,value):
    # Small recovery/final evidence must remain writable below the admission
    # floor. A low disk stops new work, never lease checks or cleanup.
    data=(json.dumps(value,indent=2)+'\n').encode('ascii');tmp=path.with_name(path.name+'.tmp');tmp.write_bytes(data);require(tmp.read_bytes()==data,'evidence_short_write');os.replace(tmp,path)
def vocabulary(plan):
    commands=set(previous.vocabulary(plan));name=Path(plan['kernel']['path']).name
    commands.update(['setenv ipaddr 192.168.1.90','setenv serverip 192.168.1.49','printenv ipaddr','printenv serverip','tftpboot 0x83000000 '+name,boot.crc_command(contract.LOAD,plan['kernel']['bytes'])]);return frozenset(commands)
class Uart(ram.Capture):
    def __init__(self,plan,guard,out):
        super().__init__({'kernel':plan['kernel'],'bootargs':plan['bootargs']},guard,out);self.allowed=vocabulary(plan)
class Host(boot.Host):
    def _guard(self,network,transfer=False):
        for path,digest in self.plan['sources'].items():require(contract.sha(path)==digest,'source_drift')
        args=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(contract.ROOT/'tools/assert_f356_context.ps1')]
        if network:args.append('-CheckNetwork')
        if transfer:args.append('-CheckTransfer')
        result=subprocess.run(args,env=desktop_ps.environment(),capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return result.returncode==0 and result.stdout.strip()==b'PASS_F356_OBSERVE_CONTEXT' and not result.stderr
    def transfer_guard(self):return self._guard(True,True)
    def initial_binding(self,identity):return json.loads(os.environ.get('OM_F356_CONTEXT','{}')).get('initial_boot_id')==identity['boot_id']
    def identity(self,name):
        if name=='f340':return super().identity(name)
        require(name=='ram','unknown_identity')
        command="printf 'boot_id='; cat /proc/sys/kernel/random/boot_id; printf 'uts='; uname -v; printf 'release='; uname -r; printf 'marker='; cat /proc/device-tree/openmitrastar,f340-watchdog-baseline; printf '\\n'; grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION="+self.plan['images']['f340']['version']+"' /etc/openmitrastar/release"
        rows=dict(line.split('=',1) for line in self.ssh(command).decode('ascii').splitlines() if '=' in line)
        rows['marker']=rows.get('marker','').removesuffix('\0')
        require(re.fullmatch('[0-9a-f-]{36}',rows.get('boot_id','')),'boot_id')
        require(rows.get('uts')=='#350 @1790006400' and rows.get('release')=='5.10.260-openmitrastar-radiohw' and rows['marker']=='F340_WATCHDOG_BASELINE','kernel_identity')
        return rows
    def preflight(self):
        raw=self.ssh(f'[ ! -d /sys/module/{MODULE} ] && [ ! -e /dev/om-f350-journal ] && [ ! -e /run/openmitrastar/watchdog/owner.lock ] && [ ! -e /run/openmitrastar/watchdog/supervisor.sock ] && sha256sum /usr/sbin/om-watchdog-supervisor {LOADER}')
        rows=raw.splitlines();require(len(rows)==2 and rows[0].split()==[previous.SUPERVISOR_SHA.encode(),b'/usr/sbin/om-watchdog-supervisor'] and rows[1].split()==[LOADER_SHA.encode(),LOADER.encode()],'baseline_owner_or_loader')
        self.storage_gate();return self.watchdog_inactive()
    def stage(self,run_id):
        require(re.fullmatch('[0-9a-f]{32}',run_id),'run_id');self.stage_dir='/run/openmitrastar/f356/'+run_id;self.supervisor=self.stage_dir+'/supervisor';self.cli=self.stage_dir+'/journal-cli';self.module_path=self.stage_dir+'/provider.ko'
        self.ssh(f'umask 077; [ ! -e {self.stage_dir} ] && mkdir -p {self.stage_dir} && chmod 700 {self.stage_dir}')
        for key,path,mode in [('provider',self.module_path,'600'),('supervisor_ram',self.supervisor,'700'),('cli',self.cli,'700')]:
            artifact=self.plan[key];self.ssh(f'cat >{path} && chmod {mode} {path}',Path(artifact['path']).read_bytes());answer=self.ssh('sha256sum '+path).split();require(answer==[artifact['sha256'].encode(),path.encode()],'ram_artifact_hash')
    def devtmpfs_ready(self):
        rows=self.ssh('cat /proc/mounts').splitlines();devices=[line.split() for line in rows if len(line.split())>=4 and line.split()[1]==b'/dev']
        require(len(devices)==1 and devices[0][2]==b'devtmpfs' and b'rw' in devices[0][3].split(b','),'devtmpfs_not_ready');return dict(mountpoint='/dev',filesystem='devtmpfs',writable=True)
    def inspect_ram(self):
        levels=self.ssh('cat /proc/sys/kernel/printk').split();require(len(levels)==4 and all(re.fullmatch(rb'[0-9]{1,2}',v) for v in levels) and 6<int(levels[0])<=15,'console_pr_info_suppressed')
        row=json.loads(self.ssh(self.supervisor+' --inspect'))
        require(row.get('event')=='inspect' and row.get('ready_for_arm')==1 and row.get('device_opened')==0 and row.get('kernel_profile_verified')==1 and row.get('required_kernel_version')=='#350 @1790006400' and row.get('control_valid')==1 and int(row.get('control','ffffffff'),16)&1==0,'ram_watchdog_profile')
        row['console_loglevel']=int(levels[0]);return row
    def launch_owner(self,token):
        require(re.fullmatch('[0-9a-f]{32}',token),'owner_token')
        command=f"umask 077; [ ! -e /run/openmitrastar/watchdog/owner.lock ] && [ ! -e /run/openmitrastar/watchdog/supervisor.sock ] || exit 71; (trap '' HUP; exec {self.supervisor} --session {token} 180000) </dev/null >{self.stage_dir}/owner.stdout 2>{self.stage_dir}/owner.stderr & printf 'F356_OWNER_PID=%s\\n' \"$!\""
        reply=self.ssh(command);match=re.fullmatch(rb'F356_OWNER_PID=([1-9][0-9]{0,9})\n',reply);require(match and int(match[1])<(1<<31),'owner_launch_pid');return int(match[1])
    def status(self,token):return json.loads(self.ssh(f'{self.supervisor} --status {token}',timeout=12))
    def arm_begin(self,token):
        rows=self.ssh(f'{self.supervisor} --request {token} 1 ARM && {self.supervisor} --request {token} 1 BEGIN {protocol.PHASE} 60000',timeout=12).splitlines();require(len(rows)==2,'arm_begin_count');return [json.loads(row) for row in rows]
    def cease(self,token):return json.loads(self.ssh(f'{self.supervisor} --request {token} 1 CEASE',timeout=12))
    def owner_files_gone(self):return self.ssh('[ ! -e /run/openmitrastar/watchdog/owner.lock ] && [ ! -e /run/openmitrastar/watchdog/supervisor.sock ] && printf GONE').strip()==b'GONE'
    def capture(self,kind,command,timeout=20):
        require(kind in ('load','observe','unload'),'capture_scope');require(self.network_guard(),'network_guard')
        p=subprocess.Popen(self.ssh_argv(command),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.children.append(p);timed_out=False;out=b'';err=b''
        try:out,err=p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as expired:
            timed_out=True;out=expired.output or b'';err=expired.stderr or b''
            if p.poll() is None:p.kill()
            try:out,err=p.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                save(self.out/(kind+'-diagnostic.json'),protocol.diagnostic(kind,out,err,None,True));raise Failure('ssh_containment_unproven') from None
            require(p.poll() is not None,'ssh_containment_unproven')
        diagnostic=protocol.diagnostic(kind,out,err,p.returncode,timed_out)
        if not hasattr(self,'operation_diagnostics'):self.operation_diagnostics={}
        self.operation_diagnostics[kind]=diagnostic;save(self.out/(kind+'-diagnostic.json'),diagnostic)
        require(len(out)<=65536 and len(err)<=65536,'ssh_output_limit');require(not timed_out,'ssh_deadline');require(p.returncode==0 and not err,'ssh_failed');return out
    def load_provider(self):
        command=f'''[ ! -d /sys/module/{MODULE} ] && [ ! -e /dev/om-f350-journal ] || exit 71
[ -f {LOADER} ] && [ -x {LOADER} ] && [ ! -L {LOADER} ] && [ "$(sha256sum {LOADER} | awk '{{print $1}}')" = {LOADER_SHA} ] || exit 72
[ "$(sha256sum {self.module_path} | awk '{{print $1}}')" = {self.plan['provider']['sha256']} ] || exit 73
load_rc=0
{LOADER} {self.module_path} 'allow_hw=1 allow_program=0' >{self.stage_dir}/load.stdout 2>{self.stage_dir}/load.stderr || load_rc=$?
printf 'load_rc=%s\n' "$load_rc"
case "$(cat {self.stage_dir}/load.stdout)" in RAM_INSMOD_OK) report=ok;; RAM_INSMOD_LOAD_FAIL) report=load_fail;; RAM_INSMOD_OPEN_FAIL) report=open_fail;; *) report=other;; esac
stderr_present=0; [ ! -s {self.stage_dir}/load.stderr ] || stderr_present=1
printf 'loader_report=%s\nloader_stderr_present=%s\n' "$report" "$stderr_present"
for field in allow_hw allow_program; do value=$(cat /sys/module/{MODULE}/parameters/$field 2>/dev/null); printf '%s=%s\n' "$field" "$value"; done
present=0; [ ! -d /sys/module/{MODULE} ] || present=1
node=0; [ ! -c /dev/om-f350-journal ] || node=1
printf 'module_present=%s\nnode_present=%s\nboot_id=' "$present" "$node"; cat /proc/sys/kernel/random/boot_id
'''
        return self.capture('load',command)
    def observe_provider(self):
        command=f'''[ "$(cat /sys/module/{MODULE}/parameters/allow_hw)" = Y ] && [ "$(cat /sys/module/{MODULE}/parameters/allow_program)" = N ] || exit 74
[ "$(sha256sum {self.cli} | awk '{{print $1}}')" = {self.plan['cli']['sha256']} ] || exit 75
exec {self.cli} observe'''
        return self.capture('observe',command)
    def unload_provider(self):
        return self.capture('unload',f"rc=0; /bin/rmmod {MODULE} || rc=$?; present=0; [ ! -d /sys/module/{MODULE} ] || present=1; node=0; [ ! -e /dev/om-f350-journal ] || node=1; printf 'unload_rc=%s\\nmodule_present=%s\\nnode_present=%s\\n' \"$rc\" \"$present\" \"$node\"")

def wait_owner(host,token,boot_id,pid):
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        try:row=protocol.owner(host.status(token),token,boot_id,pid);protocol.idle(row);return row
        except (Failure,ValueError):time.sleep(.2)
    raise Failure('owner_idle_unverified')
def wait_marker(uart,start,reset_count):
    deadline=time.monotonic()+2
    while True:
        require(not uart.failed,'uart_capture_failed');require(len(uart.reset_times)==reset_count,'reset_instead_of_observe');raw=uart.since(start)
        require(protocol.FATAL.search(raw) is None,'fault_during_observe')
        if protocol.MARKER.search(raw):return raw
        require(time.monotonic()<deadline,'observe_marker_deadline');time.sleep(.02)
def boot_ram(uart,host,plan,out,server_factory=ScopedTftpProcess):
    disk_floor();require(host.transfer_guard(),'transfer_guard');payload=load_verified_file(Path(plan['kernel']['path']),plan['kernel']['sha256'],plan['kernel']['bytes'])
    server=server_factory(guard=host.transfer_guard,output_dir=out/'tftp');host.servers.append(server)
    ram.environment(uart,'ipaddr','192.168.1.90');ram.environment(uart,'serverip','192.168.1.49')
    try:
        server.start(payload,bind='192.168.1.49',client='192.168.1.90',filename=payload.source_path.name)
        command='tftpboot 0x83000000 '+payload.source_path.name;verify_transfer(uart.command(command,timeout=300),command,payload.expected_bytes)
        receipt=server.finish();require(server.close(),'tftp_not_contained')
    except Exception:
        require(server.close(),'tftp_not_contained');raise
    require(boot.ram_crc(uart,contract.LOAD,payload.expected_bytes)==plan['kernel']['crc32'],'ram_kernel_crc');ram.iminfo(uart);ram.inactive_hardware(uart);ram.environment(uart,'bootargs',plan['bootargs'])
    start=uart.command('bootm 0x83000000',handoff=True);identity=host.wait_identity('ram',uart,start);return identity,receipt

def run(plan,out,host_factory=Host,uart_factory=Uart,ram_boot=boot_ram):
    disk_floor();host=host_factory(plan,out);uart=uart_factory(plan,host.guard,out);run_id=secrets.token_hex(16);token=secrets.token_hex(16)
    result=dict(schema='openmitrastar.f356-observe-result/v1',status='FAILED',flash_program_commands=False,flash_protection_writes=False,radio_actions=False,provider_load_attempted=False,observe_attempted=False,provider_unload_attempted=False,observe_pass=False,arm_attempted=False,software_recovery=False)
    baseline=None;ram_identity=None;owner=None;pid=None;reboot_started=False;owner_launch_attempted=False;return_attempted=False;returned=False;release_verified=True;before_reset=0;op_start=None;observe_start=None;cease_ok=False
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
        event('baseline');require(host.guard(),'lease');baseline=host.identity('f340');require(host.initial_binding(baseline),'initial_nonce_boot_mismatch');result['baseline']=baseline;result['initial_watchdog']=host.preflight()
        uart.open();reboot_started=True;event('bootbase-before-ram');host.reboot_to_prompt(uart);result['before_ram_watchdog']=ram.inactive_hardware(uart)
        result['protected_before']=boot.protected(uart,plan);result['slot_crc_before']=boot.flash_crc(uart,contract.LIVE,contract.SLOT,plan['images']['f340']['full_slot_crc32'])
        event('single-ram-boot');ram_identity,result['tftp']=ram_boot(uart,host,plan,out);require(ram_identity['boot_id']!=baseline['boot_id'],'ram_boot_not_new');result['ram_identity']=ram_identity;before_reset=len(uart.reset_times)
        event('ram-platform-ready');result['ram_platform']=host.platform('f340',out/'ram-platform');current_ram=host.identity('ram');require(current_ram['boot_id']==ram_identity['boot_id'],'ram_boot_changed_during_startup');result['ram_storage']=host.storage_gate()
        result['ram_devtmpfs']=host.devtmpfs_ready();disk_floor();host.stage(run_id);result['ram_watchdog']=host.inspect_ram();event('ram-owner-start');disk_floor();owner_launch_attempted=True;release_verified=False;pid=host.launch_owner(token);owner=wait_owner(host,token,ram_identity['boot_id'],pid);result['owner_idle']=owner
        before_reset=len(uart.reset_times);uart.invalidate_prompt();uart.stop_autoboot(120);op_start=uart.checkpoint();event('owner-arm');disk_floor();result['arm_attempted']=True
        raw_arm,raw_begin=host.arm_begin(token);arm=protocol.owner(raw_arm,token,ram_identity['boot_id'],pid,owner);protocol.armed(arm,2);begin=protocol.owner(raw_begin,token,ram_identity['boot_id'],pid,owner);protocol.armed(begin,3)
        require(arm['session_deadline_monotonic_ms']==begin['session_deadline_monotonic_ms'],'owner_deadline_changed');result['owner_arm']=arm;result['owner_begin']=begin
        event('load-readonly-provider');disk_floor();result['provider_load_attempted']=True;result['provider']=protocol.loaded(host.load_provider(),ram_identity['boot_id'])
        event('single-observe');disk_floor();observe_start=uart.checkpoint();result['observe_attempted']=True;observation=protocol.observed(host.observe_provider(),plan['expected_spi_control'])
        marker=protocol.marker_verified(wait_marker(uart,observe_start,before_reset),observation)
        require(len(uart.reset_times)==before_reset,'reset_instead_of_observe');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_during_observe');result['observation']=observation;result['observe_uart']=marker;result['observe_pass']=True
        event('unload-after-clean-release');result['provider_unload_attempted']=True;result['unload']=protocol.unloaded(host.unload_provider())
        event('planned-cease');row=protocol.owner(host.cease(token),token,ram_identity['boot_id'],pid,owner);protocol.ceased(row);result['owner_cease']=row;cease_ok=True
        require(previous.wait_reset(uart,before_reset,40),'cleanup_reset_missing');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_before_return');result['post_reset_watchdog']=ram.inactive_hardware(uart);release_verified=True
        event('readonly-f340-return');return_attempted=True;result['return']=previous.return_f340(uart,host,plan,ram_identity['boot_id'],out);returned=True
        require(not result['return']['readback_error'],'return_readback_failed');result['status']='PASS_F356_READONLY_OBSERVE_AND_F340_RETURN';event('complete')
    except Exception as error:
        result['status']='FAILED';result['error']=str(error) if isinstance(error,(Failure,protocol.ProtocolError)) else type(error).__name__
        if observe_start is not None:
            try:wait_marker(uart,observe_start,before_reset)
            except Exception as marker_error:result['marker_wait_error']=str(marker_error) if isinstance(marker_error,Failure) else type(marker_error).__name__
        diagnostic()
        if owner_launch_attempted and owner is None and ram_identity:
            try:
                raw=host.status(token);candidate=raw.get('owner_pid');owner=protocol.owner(raw,token,ram_identity['boot_id'],candidate)
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
                                try:result['recovery_cease']=protocol.owner(host.cease(token),token,ram_identity['boot_id'],pid,owner)
                                except Exception:result['recovery_cease_unconfirmed']=True
                            if cease_ok or not previous.wait_reset(uart,before_reset,80):result['software_recovery']=True;host.reboot_to_prompt(uart,software_recovery=True)
                        else:result['software_recovery']=True;host.reboot_to_prompt(uart,software_recovery=True)
                elif not uart.has_prompt():result['software_recovery']=True;host.reboot_to_prompt(uart,software_recovery=True)
                require(uart.has_prompt(),'fresh_bootbase_missing');result['post_reset_watchdog']=ram.inactive_hardware(uart);release_verified=True
                event('failed-test-readonly-return',critical=False);return_attempted=True;result['return']=previous.return_f340(uart,host,plan,(ram_identity or baseline)['boot_id'],out);returned=True;result['status']='FAIL_OBSERVE_WITH_F340_RETURN'
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
    print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))),flush=True);return 0 if result['status']=='PASS_F356_READONLY_OBSERVE_AND_F340_RETURN' else 1

def load_plan(path,digest):
    require(contract.sha(path)==digest,'plan_hash');p=json.loads(Path(path).read_text(encoding='ascii'));require(p['schema']=='openmitrastar.f356-observe-plan/v1' and p['status']=='PASS_OFFLINE_OBSERVE_GATE','plan_scope')
    require(p['images']=={'f340':contract.images()['f340']} and p['bootargs']==contract.BOOTARGS and p['protected']==contract.protected_backups(),'baseline_contract')
    require(p['allow_program'] is False and p['observation_commands']==['observe'] and p['one_shot'] is True and p['expected_spi_control']==4,'operation_scope')
    require(p['provider']['module_name']==MODULE and p['kernel']['kernel_version']=='#350 @1790006400' and p['loader']['runtime_path']==LOADER and p['loader']['sha256']==LOADER_SHA,'component_scope')
    require(Path(p['evidence_root']).resolve()==EVIDENCE_ROOT.resolve(),'evidence_root_scope')
    require(re.fullmatch('[A-Za-z0-9_.-]{1,100}',Path(p['kernel']['path']).name),'kernel_filename')
    for key in ('kernel','provider','supervisor_ram','cli','loader'):
        a=p[key];require(contract.sha(a['path'])==a['sha256'] and Path(a['path']).stat().st_size==a['bytes'],'component_hash')
    for file,expected in p['sources'].items():require(contract.sha(file)==expected,'source_drift')
    return p
def main():
    ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args();p=load_plan(a.plan,a.plan_sha256)
    if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID',hardware_actions=False)));return 0
    require(os.environ.get('OM_F356_CONTEXT') and a.output_dir and a.output_dir.is_dir(),'owning_launcher_required')
    require(a.output_dir.resolve().parent==EVIDENCE_ROOT.resolve(),'output_not_in_fixed_evidence_root');return run(p,a.output_dir)
if __name__=='__main__':raise SystemExit(main())
