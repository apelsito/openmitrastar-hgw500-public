"""Exactly one first SAVE + LOAD; preserve partial journal on failure, no re-erase."""
from pathlib import Path
import argparse,hashlib,json,os,re,secrets,subprocess,time
import f359_observe_executor as previous
import f360_protocol as protocol
import f346_install_executor as boot
import f358_install_contract as contract
import f346_powershell as desktop_ps
import f336_wdt_ram_executor as ram
from init_lyoko_device_host_key import restrict_acl
MODULE,LOADER,LOADER_SHA=previous.MODULE,previous.LOADER,previous.LOADER_SHA
SUPERVISOR_SHA=previous.SUPERVISOR_SHA
EVIDENCE_ROOT=Path('/workspace/OpenMitraStar/f360-evidence')
Failure,require=ram.Failure,ram.require
save,disk_floor=previous.save,previous.disk_floor
wait_owner,wait_reset=previous.wait_owner,previous.wait_reset
def vocabulary(plan):
 words=set(previous.vocabulary(plan))
 for offset,length in [(contract.LIVE,contract.PREFIX),(contract.STORE,contract.STORE_BYTES)]:words.add(boot.read_command(offset,length));words.add(boot.crc_command(contract.READBACK,length))
 return frozenset(words)
class Uart(ram.Capture):
 def __init__(self,plan,guard,out):super().__init__({'kernel':plan['images']['f358'],'bootargs':plan['bootargs']},guard,out);self.allowed=vocabulary(plan)
class Host(previous.Host):
 def arm_begin(self,token):
  rows=self.ssh(f'{self.supervisor} --request {token} 1 ARM && {self.supervisor} --request {token} 1 BEGIN {protocol.PHASE} 60000',timeout=12).splitlines();require(len(rows)==2,'arm_begin_count');return [json.loads(row) for row in rows]
 def _guard(self,network,transfer=False):
  require(not transfer,'no_tftp_in_f360')
  for path,digest in self.plan['sources'].items():require(contract.sha(path)==digest,'source_drift')
  args=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(contract.ROOT/'tools/assert_f360_context.ps1')]
  if network:args.append('-CheckNetwork')
  result=subprocess.run(args,env=desktop_ps.environment(),capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));return result.returncode==0 and result.stdout.strip()==b'PASS_F360_SAVE_CONTEXT' and not result.stderr
 def initial_binding(self,identity):return json.loads(os.environ.get('OM_F360_CONTEXT','{}')).get('initial_boot_id')==identity['boot_id']
 def stage(self,run_id):
  require(re.fullmatch('[0-9a-f]{32}',run_id),'run_id');self.stage_dir='/run/openmitrastar/f360/'+run_id;self.supervisor=self.stage_dir+'/supervisor';self.cli=self.stage_dir+'/journal-cli';self.module_path=previous.PROVIDER;self.payload_path=self.stage_dir+'/payload'
  self.ssh(f'umask 077; [ ! -e {self.stage_dir} ] && mkdir -p {self.stage_dir} && chmod 700 {self.stage_dir} && cp {previous.SUPERVISOR} {self.supervisor} && cp {previous.CLI} {self.cli} && chmod 700 {self.supervisor} {self.cli}')
  payload=self.plan['payload'];data=Path(payload['path']).read_bytes();require(len(data)==payload['bytes'] and hashlib.sha256(data).hexdigest()==payload['sha256'],'private_payload_drift')
  self.ssh(f'umask 077; cat >{self.payload_path} && chmod 600 {self.payload_path}',data)
  for path,expected in [(self.supervisor,SUPERVISOR_SHA),(self.cli,self.plan['cli']['sha256']),(self.payload_path,payload['sha256'])]:require(self.ssh('sha256sum '+path).split()==[expected.encode(),path.encode()],'staged_hash')
 def current_payload(self):
  row=self.ssh('sha256sum /run/openmitrastar/config/active.conf').split();require(row==[self.plan['payload']['sha256'].encode(),b'/run/openmitrastar/config/active.conf'],'active_configuration_changed');return dict(sha256=self.plan['payload']['sha256'],current=True)
 def store_snapshot(self,tag):
  require(tag in ('before','after'),'snapshot_scope')
  rows=self.ssh('cat /proc/mtd').splitlines();matches=[]
  for row in rows:
   m=re.fullmatch(rb'mtd([0-9]+):\s+([0-9a-fA-F]{8})\s+([0-9a-fA-F]{8})\s+"lyoko_store"',row)
   if m:matches.append(m)
  require(len(matches)==1 and matches[0][1]==b'4' and int(matches[0][2],16)==0x1c0000 and int(matches[0][3],16)==0x10000,'unique_store_geometry')
  flags=int(self.ssh('cat /sys/class/mtd/mtd4/flags').strip(),0);require(not flags&0x400,'store_mtd_not_readonly');require(self.ssh('[ -c /dev/mtd4 ] && printf MTDCHAR').strip()==b'MTDCHAR','store_character_node')
  private=self.out/'private';private.mkdir(exist_ok=True);restrict_acl(private,directory=True);chunks=[];parts=[]
  for index,name in [(0,'dc'),(1,'dd')]:
   raw=self.ssh(f'dd if=/dev/mtd4 bs=65536 skip={index} count=1 2>/dev/null',timeout=60);require(len(raw)==65536,'store_short_read')
   path=private/(tag+'-'+name+'.bin')
   with path.open('xb') as stream:require(stream.write(raw)==len(raw),'private_snapshot_short_write')
   restrict_acl(path,directory=False);chunks.append(raw);parts.append(dict(name=name,path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
  full=self.ssh('sha256sum /dev/mtd4',timeout=60).split();require(len(full)==2 and re.fullmatch(rb'[0-9a-f]{64}',full[0]) and full[1]==b'/dev/mtd4','store_sha256_response')
  data=b''.join(chunks);expected=Path(self.plan['expected']['artifacts']['expected-dc-dd.bin']['path']).read_bytes()
  return dict(parts=parts,pair_sha256=hashlib.sha256(data).hexdigest(),pair_bytes=len(data),store_sha256=full[0].decode(),all_pair_ff=all(value==255 for value in data),expected_pair_byte_equal=data==expected,read_only_mtd=True,raw_public=False)
 def capture(self,kind,command,timeout=30):
  require(kind in ('module-load','save','load-readback','unload'),'capture_scope');require(self.network_guard(),'network_guard')
  process=subprocess.Popen(self.ssh_argv(command),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.children.append(process);timed=False;out=b'';err=b''
  try:out,err=process.communicate(timeout=timeout)
  except subprocess.TimeoutExpired as expired:
   timed=True;out=expired.output or b'';err=expired.stderr or b''
   if process.poll() is None:process.kill()
   try:out,err=process.communicate(timeout=3)
   except subprocess.TimeoutExpired:save(self.out/(kind+'-diagnostic.json'),protocol.diagnostic(kind,out,err,None,True));raise Failure('ssh_containment_unproven') from None
   require(process.poll() is not None,'ssh_containment_unproven')
  record=protocol.diagnostic(kind,out,err,process.returncode,timed)
  if not hasattr(self,'operation_diagnostics'):self.operation_diagnostics={}
  self.operation_diagnostics[kind]=record;save(self.out/(kind+'-diagnostic.json'),record)
  require(len(out)<=8192 and len(err)<=8192,'metadata_output_limit');require(not timed,'ssh_deadline');require(process.returncode==0 and not err,'ssh_failed');return out
 def load_provider(self):
  # Reuse the proven loader command body, changing only the explicit gate.
  original=self.capture
  def program_capture(kind,command,timeout=20):
   require(kind=='load' and command.count("'allow_hw=1 allow_program=0'")==1,'loader_template_drift')
   return original('module-load',command.replace("'allow_hw=1 allow_program=0'","'allow_hw=1 allow_program=1'"),timeout)
  self.capture=program_capture
  try:return super().load_provider()
  finally:self.capture=original
 def save_config(self):
  command=f'''[ "$(cat /sys/module/{MODULE}/parameters/allow_hw)" = Y ] && [ "$(cat /sys/module/{MODULE}/parameters/allow_program)" = Y ] || exit 74
[ "$(sha256sum {self.payload_path} | awk '{{print $1}}')" = {self.plan['payload']['sha256']} ] || exit 75
[ "$(sha256sum {self.cli} | awk '{{print $1}}')" = {self.plan['cli']['sha256']} ] || exit 76
exec {self.cli} save <{self.payload_path}'''
  return self.capture('save',command)
 def load_config(self):
  command=f'''rc=0
{self.cli} load >{self.stage_dir}/readback 2>{self.stage_dir}/readback.stderr || rc=$?
printf 'readback_rc=%s\n' "$rc"
present=0; [ ! -s {self.stage_dir}/readback.stderr ] || present=1; printf 'stderr_present=%s\n' "$present"
if [ "$rc" = 0 ]; then printf 'bytes='; wc -c <{self.stage_dir}/readback; printf 'sha256='; sha256sum {self.stage_dir}/readback | awk '{{print $1}}'; fi'''
  return self.capture('load-readback',command)

def return_after_save(uart,host,plan,old_boot,out,expected_saved=False):
 observed=ram.inactive_hardware(uart);error=None;proof={}
 try:
  proof['protected']=boot.protected(uart,plan);proof['firmware_prefix_crc32']=boot.flash_crc(uart,contract.LIVE,contract.PREFIX,plan['expected']['expected_after_save']['firmware_prefix_crc32'])
  proof['store_crc32']=boot.flash_crc(uart,contract.STORE,contract.STORE_BYTES)
  proof['full_slot_crc32']=boot.flash_crc(uart,contract.LIVE,contract.SLOT)
 except Exception as failure:error=str(failure) if isinstance(failure,Failure) else type(failure).__name__
 identity=boot.boot_written(uart,host,plan,'f358',old_boot,prefix_only=True);platform=host.platform('f358',out/'return-platform');watchdog=host.watchdog_inactive();require(host.owner_files_gone(),'owner_survived_reset')
 snapshot=None;persisted=False
 try:
  snapshot=host.store_snapshot('after');art=plan['expected']['artifacts'];persisted=snapshot['expected_pair_byte_equal'] is True and snapshot['pair_sha256']==art['expected-dc-dd.bin']['sha256'] and snapshot['store_sha256']==art['expected-store.bin']['sha256'] and proof.get('store_crc32')==art['expected-store.bin']['crc32'] and proof.get('full_slot_crc32')==plan['expected']['expected_after_save']['full_slot_crc32']
  if expected_saved and not persisted:error=error or 'durable_store_mismatch'
 except Exception as failure:error=error or ('postboot_snapshot_'+(str(failure) if isinstance(failure,Failure) else type(failure).__name__))
 state='expected-record-present' if persisted else ('original-pair-ff' if snapshot and snapshot['all_pair_ff'] else 'partial-or-unverified-journal')
 return dict(post_reset_watchdog=observed,readback=proof,readback_error=error,identity=identity,platform=platform,watchdog=watchdog,store_snapshot=snapshot,persisted_expected_record=persisted,journal_state=state,repair_deferred=not persisted,physical_ff_restore_performed=False)

def run(plan,out,host_factory=Host,uart_factory=Uart):
    disk_floor();host=host_factory(plan,out);uart=uart_factory(plan,host.guard,out);run_id=secrets.token_hex(16);token=secrets.token_hex(16)
    result=dict(schema='openmitrastar.f360-save-result/v1',status='FAILED',flash_program_commands=True,flash_protection_writes=False,radio_actions=False,provider_load_attempted=False,save_attempted=False,provider_unload_attempted=False,save_pass=False,arm_attempted=False,software_recovery=False)
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
    try:
        event('baseline');require(host.guard(),'lease');baseline=host.identity('f358');require(host.initial_binding(baseline),'initial_nonce_boot_mismatch');result['baseline']=baseline;result['initial_watchdog']=host.preflight()
        result['platform_before']=host.platform('f358',out/'platform-before');current=host.identity('f358');require(current['boot_id']==baseline['boot_id'],'boot_changed_before_observe');active_identity=baseline
        result['storage']=host.storage_gate();result['current_payload']=host.current_payload();result['store_before']=host.store_snapshot('before');require(result['store_before']['all_pair_ff'] and result['store_before']['store_sha256']==plan['expected']['original']['store_sha256'],'store_not_original_ff');result['devtmpfs']=host.devtmpfs_ready();uart.open();before_reset=len(uart.reset_times);disk_floor();host.stage(run_id);result['watchdog_profile']=host.inspect_current()
        event('owner-start');disk_floor();owner_launch_attempted=True;reboot_started=True;release_verified=False;pid=host.launch_owner(token);owner=wait_owner(host,token,baseline['boot_id'],pid);result['owner_idle']=owner
        before_reset=len(uart.reset_times);uart.invalidate_prompt();uart.stop_autoboot(120);op_start=uart.checkpoint();event('owner-arm');disk_floor();result['arm_attempted']=True
        raw_arm,raw_begin=host.arm_begin(token);arm=protocol.owner(raw_arm,token,active_identity['boot_id'],pid,owner);protocol.armed(arm,2);begin=protocol.owner(raw_begin,token,active_identity['boot_id'],pid,owner);protocol.armed(begin,3)
        require(arm['session_deadline_monotonic_ms']==begin['session_deadline_monotonic_ms'],'owner_deadline_changed');result['owner_arm']=arm;result['owner_begin']=begin
        event('load-program-provider');disk_floor();result['provider_load_attempted']=True;result['provider']=protocol.loaded(host.load_provider(),active_identity['boot_id'])
        event('single-save');disk_floor();result['save_attempted']=True;result['save_response']=protocol.saved(host.save_config(),plan['payload'])
        require(len(uart.reset_times)==before_reset,'reset_during_save');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_during_save')
        event('load-readback');result['load_readback_attempted']=True;result['load_readback']=protocol.loaded_payload(host.load_config(),plan['payload']);result['save_pass']=True
        require(len(uart.reset_times)==before_reset,'reset_during_readback');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_during_readback')
        event('unload-after-clean-release');result['provider_unload_attempted']=True;result['unload']=protocol.unloaded(host.unload_provider())
        event('planned-cease');row=protocol.owner(host.cease(token),token,active_identity['boot_id'],pid,owner);protocol.ceased(row);result['owner_cease']=row;cease_ok=True
        require(wait_reset(uart,before_reset,40),'cleanup_reset_missing');require(protocol.FATAL.search(uart.since(op_start)) is None,'fault_before_return');result['post_reset_watchdog']=ram.inactive_hardware(uart);release_verified=True
        event('readonly-f358-return');return_attempted=True;result['return']=return_after_save(uart,host,plan,active_identity['boot_id'],out,expected_saved=True);returned=True
        require(not result['return']['readback_error'],'return_readback_failed');result['status']='PASS_F360_CONFIG_SAVED_AND_PERSISTED';event('complete')
    except Exception as error:
        result['status']='FAILED';result['error']=str(error) if isinstance(error,(Failure,protocol.ProtocolError)) else type(error).__name__
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
                event('failed-test-readonly-return',critical=False);return_attempted=True;result['return']=return_after_save(uart,host,plan,(active_identity or baseline)['boot_id'],out,expected_saved=False);returned=True;result['status']='FAIL_SAVE_WITH_F358_RETURN_NO_REERASE'
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
    print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))),flush=True);return 0 if result['status']=='PASS_F360_CONFIG_SAVED_AND_PERSISTED' else 1

def load_plan(path,digest):
 require(contract.sha(path)==digest,'plan_hash');p=json.loads(Path(path).read_text(encoding='ascii'));require(p['schema']=='openmitrastar.f360-save-plan/v1' and p['status']=='PASS_OFFLINE_FIRST_SAVE_GATE','plan_scope')
 require(p['images']=={'f358':contract.images()['f358']} and p['bootargs']==contract.BOOTARGS and p['protected']==contract.protected_backups(),'image_contract')
 require(p['allow_program'] is True and p['operations']==['save','load'] and p['save_calls']==1 and p['one_shot'] is True and p['rollback_erase_allowed'] is False,'save_scope')
 require(Path(p['evidence_root']).resolve()==EVIDENCE_ROOT.resolve(),'evidence_root_scope')
 for key in ('provider','cli','supervisor','loader','payload'):
  item=p[key];require(contract.sha(item['path'])==item['sha256'] and Path(item['path']).stat().st_size==item['bytes'],'artifact_drift')
 require(p['supervisor']['sha256']==SUPERVISOR_SHA and p['provider']['sha256']=='ab88ec603c18cd013f0de1d79eed1ea9c696ca97d2b589e0e8b9aaa8f9251cd4','component_identity')
 for file,expected in p['sources'].items():require(contract.sha(file)==expected,'source_drift')
 return p
def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args();p=load_plan(a.plan,a.plan_sha256)
 if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID',hardware_actions=False)));return 0
 require(os.environ.get('OM_F360_CONTEXT') and a.output_dir and a.output_dir.is_dir() and a.output_dir.resolve().parent==EVIDENCE_ROOT.resolve(),'owning_launcher_required');return run(p,a.output_dir)
if __name__=='__main__':raise SystemExit(main())
