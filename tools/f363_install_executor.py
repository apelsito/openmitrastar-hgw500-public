"""F363 firmware-prefix install preserving the committed journal; F362 return.

Import/default CLI are file-only. Explicit execution requires the parent-owned
F363 lease/nonce context. Only the mtd4 prefix can be erased or programmed.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys,time
import f363_install_contract as c
import f346_powershell as desktop_ps
import f336_wdt_ram_executor as base
import f363_thermal_status as thermal
from f362_recovery_delta import serial_reboot_to_prompt, verify_ethernet_response, ethernet_command, clear_pending_break
from init_lyoko_device_host_key import restrict_acl
from f325_ethernet_server_process import ScopedTftpProcess
from f325_scoped_tftp import load_verified_file
from f325_ethernet_ram_gate import response_lines,verify_silent,verify_environment,verify_transfer,verify_filesize
from bootbase_contract_emulator import validate_bootbase_slot,image_to_dict

Failure=base.Failure
require=base.require
def crc_command(address,size):return f'crc32 0x{address:08x} 0x{size:08x} 0x{c.SCRATCH:08x}'
def read_command(offset,size,address=c.READBACK):return f'spi_flash read 0x{offset:08x} 0x{address:08x} 0x{size:08x}'
def write_command(image):return f"spi_flash write 0x{c.LIVE:08x} 0x{c.LOAD:08x} 0x{image['bytes']:08x}"
ERASE_COMMAND=f'spi_flash erase 0x{c.LIVE:08x} 0x{c.PREFIX:08x}'
def vocabulary(plan):
    words={'md.l 0xe0000004 1','md.l 0xf4000000 1','md.l 0xf4000008 1','md.l 0x84000000 1','printenv bootcmd','printenv bootselect','printenv filesize',
      'setenv ipaddr 192.168.1.90','setenv serverip 192.168.1.49','printenv ipaddr','printenv serverip','setenv bootargs '+plan['bootargs'],'printenv bootargs','iminfo 0x83000000','bootm 0x83000000'}
    regions=[(p['offset'],p['bytes']) for p in plan['protected']['parts']]+[(c.LIVE,c.SLOT),(c.LIVE,c.PREFIX),(c.STORE,c.STORE_BYTES)]
    for offset,n in regions:words.add(read_command(offset,n));words.add(crc_command(c.READBACK,n))
    words.add(read_command(c.LIVE,c.SLOT,c.LOAD));words.add(crc_command(c.LOAD,c.SLOT))
    for image in plan['images'].values():
        words.add('tftpboot 0x83000000 '+Path(image['path']).name);words.add(crc_command(c.LOAD,image['bytes']));words.add(crc_command(c.READBACK,image['bytes']))
        words.add(f"cmp.b 0x{c.LOAD:08x} 0x{c.READBACK:08x} 0x{image['bytes']:08x}")
        words.add(read_command(c.LIVE,image['bytes'],c.LOAD))
    return frozenset(words)
class Uart(base.Capture):
    def __init__(self,plan,guard,out):
        super().__init__({'kernel':plan['images']['f363'],'bootargs':plan['bootargs']},guard,out)
        self.kernel_handoff_start=None;self.serial_recovery_record={};self.allowed=vocabulary(plan);self.write_in_flight=False;self.erase_requested=False;self.write_requested=False;self._images=plan['images'];self._write_commands=set();self._writer_enabled=False;self._cycle_erased=False;self._cycle_written=False
    def mutate(self,command):
        require(self._writer_enabled,'write_cycle_not_enabled')
        require(command==ERASE_COMMAND or command in self._write_commands,'write_command_scope')
        require(not self._cycle_written and (not self._cycle_erased if command==ERASE_COMMAND else self._cycle_erased),'write_order_or_repeat')
        self.write_in_flight=True
        if command==ERASE_COMMAND:self.erase_requested=True;self._cycle_erased=True
        else:self.write_requested=True;self._cycle_written=True
        self.allowed=frozenset(set(self.allowed)|{command})
        try:
            response=self.command(command,timeout=300)
            # Even a refused command is not in flight once its NEW prompt arrives.
            self.write_in_flight=False
            return response
        finally:self.allowed=frozenset(set(self.allowed)-{command})
    def enable_writer(self,image):
        require(not self.write_in_flight and image in self._images.values(),'write_image_not_pinned');self._write_commands={write_command(image)};self._writer_enabled=True;self._cycle_erased=False;self._cycle_written=False
    def disable_writer(self):self._writer_enabled=False

class Host(base.Host):
    def __init__(self,plan,out):
        super().__init__(plan,out);self.servers=[];self.network_check_failures=0
    def contain(self):
        server_results=[]
        for server in self.servers:
            try:server_results.append(server.close() is True)
            except Exception:server_results.append(False)
        processes=super().contain()
        return processes and all(server_results)
    def initial_binding(self,identity):
        return json.loads(os.environ.get('OM_F363_CONTEXT','{}')).get('initial_boot_id')==identity['boot_id']
    def _guard(self,network):
        for path,digest in self.plan['sources'].items():require(c.sha(path)==digest,'source_drift')
        argv=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/assert_f363_context.ps1')]
        if network:argv.append('-CheckNetwork')
        p=subprocess.run(argv,env=desktop_ps.environment(),capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return p.returncode==0 and p.stdout.strip()==b'PASS_F363_INSTALL_CONTEXT' and not p.stderr
    def guard(self):return self._guard(False)
    def network_guard(self):
        passed=self._guard(True)
        if not passed:self.network_check_failures+=1
        return passed
    def ssh(self,command,data=b'',timeout=20,allow_disconnect=False):
        require(self.network_guard(),'network_guard')
        return super().ssh(command,data,timeout,allow_disconnect)
    def backup_reference(self):
        image=self.plan['images']['f362'];data=Path(image['path']).read_bytes();require(hashlib.sha256(data).hexdigest()==image['sha256'],'backup_image_hash')
        private=c.DEVICE.parent/'analysis'/('f363-private-backup-'+self.out.name);private.mkdir(parents=True,exist_ok=False);restrict_acl(private,directory=True)
        path=private/'backup-reference-f362.webformat.bin'
        with path.open('xb') as stream:require(stream.write(data)==len(data),'backup_short_write')
        restrict_acl(path,directory=False);require(c.sha(path)==image['sha256'],'backup_copy_hash')
        return dict(path=str(path),sha256=image['sha256'],fresh_physical_dump=False,private_acl_applied=True)
    def identity(self,name):
        image=self.plan['images'][name]
        command="printf 'boot_id='; cat /proc/sys/kernel/random/boot_id; printf 'uts='; uname -v; printf 'f340='; if [ -r /proc/device-tree/openmitrastar,f340-watchdog-baseline ]; then cat /proc/device-tree/openmitrastar,f340-watchdog-baseline; fi; printf '\\nf336='; if [ -r /proc/device-tree/openmitrastar,f336-wdt-ram ]; then cat /proc/device-tree/openmitrastar,f336-wdt-ram; fi; printf '\\n'; grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION="+image['version']+"' /etc/openmitrastar/release"
        data=self.ssh(command);rows=dict(s.split('=',1) for s in data.decode('ascii').splitlines() if '=' in s)
        for key in ('f340','f336'):
            rows[key]=rows.get(key,'').removesuffix('\0');require('\0' not in rows[key],'marker_encoding')
        require(re.fullmatch('[0-9a-f-]{36}',rows.get('boot_id','')),'boot_id')
        require(rows.get('uts','').split()[:1]==[image['kernel_build']] and rows['f340']==image['marker'] and not rows['f336'],'kernel_identity')
        return rows
    def wait_identity(self,name,uart,start,timeout=180):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            require(not uart.failed,'uart_capture_failed');require(not base.PROMPT.search(uart.since(start)),'bootm_returned_no_retry')
            try:return self.identity(name)
            except Failure as error:
                if str(error) not in ('ssh_failed','ssh_deadline','kernel_identity','boot_id','network_guard'):raise
            time.sleep(1)
        raise Failure('boot_identity_timeout')
    def platform(self,name,out):
        # Run the existing read-only gate in-process: it bounds/reaps its own
        # SSH child, so no orphan gate process can overlap subsequent flash.
        require(self.network_guard(),'network_guard_before_platform')
        import post_flash_f214_device_gate as gate
        image=self.plan['images'][name];saved=sys.argv
        sys.argv=[str(c.ROOT/'tools/post_flash_f214_device_gate.py'),'--host','192.168.1.90','--wait-seconds','180','--output-dir',str(out),'--device-dir',image['directory'],'--expected-version',image['version'],'--known-hosts-name',image['known_hosts']]
        try:code=gate.main()
        finally:sys.argv=saved
        data=json.loads((out/'status.json').read_text(encoding='utf-8'))
        require(code==0 and data['status']=='PASS' and len(data['checks'])==27 and all(v is True for v in data['checks'].values()),'platform_gate')
        return dict(status='PASS',checks=27,result=str(out/'status.json'),sha256=c.sha(out/'status.json'))
    def reboot_to_prompt(self,uart,software_recovery=False):
        if software_recovery:return serial_reboot_to_prompt(self,uart)
        mask=int(self.ssh('cat /proc/sys/kernel/sysrq').strip());require(mask==1 or bool(mask&128),'sysrq_reboot_disabled')
        return super().reboot_to_prompt(uart,software_recovery=False)
    def verify_ethernet(self):
        return verify_ethernet_response(self.ssh(ethernet_command()))
    def verify_thermal_disabled(self):
        return thermal.validate(self.ssh(thermal.command()))
    def verify_store(self):
        rows=self.ssh('cat /proc/mtd').splitlines();matches=[row for row in rows if row.endswith(b'"lyoko_store"')]
        require(len(matches)==1 and re.fullmatch(rb'mtd4:\s+001c0000\s+00010000\s+"lyoko_store"',matches[0]),'unique_store_geometry')
        flags=int(self.ssh('cat /sys/class/mtd/mtd4/flags').strip(),0);require(not flags&0x400,'store_mtd_not_readonly')
        output=self.ssh('[ -c /dev/mtd4 ] && sha256sum /dev/mtd4',timeout=60).split()
        require(output==[self.plan['store']['sha256'].encode(),b'/dev/mtd4'],'preserved_store_changed')
        return dict(sha256=self.plan['store']['sha256'],bytes=self.plan['store']['bytes'],read_only_mtd=True)
    def verify_configuration(self):
        command="printf 'ready='; cat /run/openmitrastar/config-journal/ready; cat /run/openmitrastar/config-journal/state; printf 'active_sha256='; sha256sum /run/openmitrastar/config/active.conf | awk '{print $1}'; printf 'allow_hw='; cat /sys/module/qtn_f356_journal/parameters/allow_hw; printf 'allow_program='; cat /sys/module/qtn_f356_journal/parameters/allow_program"
        pairs=[line.split('=',1) for line in self.ssh(command).decode('ascii').splitlines()]
        require(all(len(row)==2 for row in pairs) and len({row[0] for row in pairs})==len(pairs),'config_boot_response')
        rows=dict(pairs);expected=self.plan['boot_acceptance']['payload_sha256']
        require(rows==dict(ready='F361_READY',slot='B',sequence='2',sha256=expected,source='journal',active_sha256=expected,allow_hw='Y',allow_program='Y'),'journal_not_applied_or_backend_unready')
        return dict(source='journal',sequence=2,slot='B',active_sha256=expected,backend_allow_hw=True,backend_allow_program=True)
    def watchdog_inactive(self):
        row=json.loads(self.ssh('/usr/sbin/om-watchdog-supervisor --inspect'))
        require(row.get('event')=='inspect' and row.get('ready_for_arm')==1 and row.get('device_opened')==0 and row.get('control_valid')==1 and int(row.get('control','ffffffff'),16)&1==0,'watchdog_not_inactive')
        return row

def ram_crc(uart,address,size):
    cmd=crc_command(address,size);verify_silent(uart.command(cmd),cmd)
    cmd='md.l 0x84000000 1';raw=uart.command(cmd);response_lines(raw,cmd);return f'{base.word(raw,c.SCRATCH):08x}'
def flash_read(uart,offset,size,address=c.READBACK):
    cmd=read_command(offset,size,address);raw=uart.command(cmd,timeout=240)
    require(response_lines(raw,cmd)==[f'Read: flash=0x{offset:x} mem=0x{address:x} size={size} ret_size={size}'],'flash_read_not_confirmed')
def flash_crc(uart,offset,size,expected=None):
    flash_read(uart,offset,size);actual=ram_crc(uart,c.READBACK,size)
    if expected is not None:require(actual==expected,'flash_crc_mismatch')
    return actual
def selector(uart):
    for name,value in [('bootcmd','bootselect'),('bootselect','0')]:
        cmd='printenv '+name;verify_environment(uart.command(cmd),cmd,name,value)
def protected(uart,plan):
    result={}
    for item in plan['protected']['parts']:result[item['partition']]=flash_crc(uart,item['offset'],item['bytes'],item['crc32'])
    return result
def domain(uart,plan,store_crc):
    require(not uart.write_in_flight,'flash_command_in_flight')
    watchdog=base.inactive_hardware(uart);selector(uart);parts=protected(uart,plan)
    observed=flash_crc(uart,c.STORE,c.STORE_BYTES,store_crc)
    return dict(watchdog=watchdog,protected=parts,store_crc32=observed)
def transfer(uart,host,plan,image,out,server_factory=ScopedTftpProcess):
    require(host.network_guard(),'network_guard_before_transfer')
    payload=load_verified_file(Path(image['path']),image['sha256'],image['bytes']);server=server_factory(guard=host.guard,output_dir=out)
    host.servers.append(server)
    closed=False
    try:
        server.start(payload,bind='192.168.1.49',client='192.168.1.90',filename=payload.source_path.name)
        base.environment(uart,'ipaddr','192.168.1.90');base.environment(uart,'serverip','192.168.1.49')
        cmd='tftpboot 0x83000000 '+payload.source_path.name;verify_transfer(uart.command(cmd,timeout=300),cmd,payload.expected_bytes)
        verify_filesize(uart.command('printenv filesize'),'printenv filesize',payload.expected_bytes)
        receipt=server.finish();require(server.close(),'server_containment');closed=True
        require(ram_crc(uart,c.LOAD,image['bytes'])==image['crc32'],'candidate_ram_crc');base.iminfo(uart)
        return receipt
    finally:
        if not closed:require(server.close(),'server_containment')
def write_image(uart,host,plan,image,out,store_crc,server_factory=ScopedTftpProcess):
    receipt=transfer(uart,host,plan,image,out/'tftp',server_factory)
    before=domain(uart,plan,store_crc)
    # The image stays at 83000000; all protection/readback work uses 86000000.
    require(ram_crc(uart,c.LOAD,image['bytes'])==image['crc32'],'candidate_changed_before_erase')
    uart.enable_writer(image)
    try:
        response=uart.mutate(ERASE_COMMAND);require(response_lines(response,ERASE_COMMAND)==[f'Erase: flash=0x{c.LIVE:x} size={c.PREFIX}'],'erase_receipt')
        flash_crc(uart,c.LIVE,c.PREFIX,plan['erased_prefix_crc32'])
        # Non-FF journal is checked immediately after erase, before programming.
        flash_crc(uart,c.STORE,c.STORE_BYTES,store_crc)
        cmd=write_command(image);response=uart.mutate(cmd)
        require(response_lines(response,cmd)==[f"Write: flash=0x{c.LIVE:x} mem=0x{c.LOAD:x} size={image['bytes']} ret_size={image['bytes']}"],'write_receipt')
        flash_read(uart,c.LIVE,c.SLOT);require(ram_crc(uart,c.READBACK,c.SLOT)==image['full_slot_crc32'],'full_slot_readback_crc')
        cmd=f"cmp.b 0x{c.LOAD:08x} 0x{c.READBACK:08x} 0x{image['bytes']:08x}";rows=response_lines(uart.command(cmd,timeout=180),cmd)
        require(rows==[f"Total of {image['bytes']} bytes were the same"],'candidate_byte_compare')
        after=domain(uart,plan,store_crc)
        return dict(image=image['sha256'],bytes=image['bytes'],full_slot_crc32=image['full_slot_crc32'],byte_compare=True,prewrite=before,postwrite=after,tftp=receipt,hardware_sha256_observed=None)
    finally:uart.disable_writer()
def boot_written(uart,host,plan,name,previous_boot,prefix_only=False):
    image=plan['images'][name]
    size=image['bytes'] if prefix_only else c.SLOT;expected=image['crc32'] if prefix_only else image['full_slot_crc32']
    flash_read(uart,c.LIVE,size,c.LOAD);require(ram_crc(uart,c.LOAD,size)==expected,'flash_boot_image_crc');base.iminfo(uart)
    base.environment(uart,'bootargs',plan['bootargs']);start=uart.command('bootm 0x83000000',handoff=True)
    uart.kernel_handoff_start=start
    identity=host.wait_identity(name,uart,start);require(identity['boot_id']!=previous_boot,'boot_not_new');return identity

def run(plan,out,host_factory=Host,uart_factory=Uart,server_factory=ScopedTftpProcess):
    host=host_factory(plan,out);uart=uart_factory(plan,host.guard,out)
    result=dict(schema='openmitrastar.f363-install-result/v1',status='FAILED',stage='baseline',target='mtd4/linux_live',erase_bytes=c.PREFIX,radio_tests_performed=False,watchdog_arm_requested=False,rollback_attempted=False)
    original=None;store_crc=None;reboot_started=False;restore_boot_attempted=False
    def checkpoint(stage):
        result['stage']=stage
        with (out/'events.jsonl').open('a',encoding='ascii') as stream:stream.write(json.dumps(dict(stage=stage,monotonic_ms=round(time.monotonic()*1000)))+'\n')
    try:
        require(host.guard(),'lease');original=host.identity('f362');require(host.initial_binding(original),'initial_nonce_boot_mismatch');result['baseline']=original
        result['baseline_watchdog']=host.watchdog_inactive();result['store_before']=host.verify_store();result['rollback_reference']=host.backup_reference()
        uart.open();reboot_started=True;checkpoint('bootbase-preflight');host.reboot_to_prompt(uart)
        base.inactive_hardware(uart);selector(uart);result['protected_before']=protected(uart,plan)
        store_crc=flash_crc(uart,c.STORE,c.STORE_BYTES,plan['store']['crc32']);result['store_crc32']=store_crc
        result['current_f362_crc32']=flash_crc(uart,c.LIVE,c.SLOT,plan['images']['f362']['full_slot_crc32'])
        checkpoint('install-f363');result['writer']=write_image(uart,host,plan,plan['images']['f363'],out/'install',store_crc,server_factory)
        checkpoint('boot-f363');result['f363_identity']=boot_written(uart,host,plan,'f363',original['boot_id'])
        checkpoint('platform-f363');result['platform']=host.platform('f363',out/'platform-f363');result['watchdog']=host.watchdog_inactive();result['store_after']=host.verify_store();result['configuration_boot']=host.verify_configuration();result['ethernet']=host.verify_ethernet();result['thermal_default']=host.verify_thermal_disabled()
        result['status']='PASS_F363_PRESERVED_JOURNAL';checkpoint('complete-f363-kept')
    except Exception as error:
        result['error']=str(error) if isinstance(error,Failure) else type(error).__name__
        can_recover=reboot_started and original is not None and not uart.write_in_flight
        if can_recover:
            try:
                require(host.contain(),'prior_helpers_not_contained')
                if not uart.has_prompt():host.reboot_to_prompt(uart,software_recovery=True)
                mutated=uart.erase_requested or uart.write_requested
                if mutated:
                    require(store_crc is not None,'original_store_unknown');domain(uart,plan,store_crc)
                    result['rollback_attempted']=True;checkpoint('restore-f362')
                    result['restore_writer']=write_image(uart,host,plan,plan['images']['f362'],out/'restore',store_crc,server_factory)
                else:base.inactive_hardware(uart)
                checkpoint('boot-f362-return');restore_boot_attempted=True
                result['returned_identity']=boot_written(uart,host,plan,'f362',original['boot_id'],prefix_only=not mutated);result['return_platform']=host.platform('f362',out/'platform-f362');result['returned_watchdog']=host.watchdog_inactive();result['returned_store']=host.verify_store()
                result['status']='FAILED_F363_WITH_F362_AND_PRESERVED_JOURNAL';checkpoint('complete-f362-returned')
            except Exception as recovery:
                result['recovery_error']=str(recovery) if isinstance(recovery,Failure) else type(recovery).__name__
                result['status']='FAILED_RECOVERY_UNPROVEN_NO_RETRY'
        elif reboot_started:result['status']='STOP_UNCERTAIN_NO_AUTOMATIC_WRITE'
    finally:
        try:result['children_contained']=host.contain()
        except Exception:result['children_contained']=False
        result['break_cleanup_verified']=clear_pending_break(uart)
        try:result['uart']=uart.close()
        except Exception:result['uart']={}
        result['containment_confirmed']=result['children_contained'] and result['uart'].get('reader_stopped') is True and result['uart'].get('port_closed') is True
        try:result['final_domain_guard']=host.guard() is True
        except Exception:result['final_domain_guard']=False
        result['retain_lease_required']=not result['containment_confirmed'] or uart.write_in_flight or not result['final_domain_guard'] or bool(getattr(uart,'serial_recovery_record',{}).get('break_attempted') and not getattr(uart,'serial_recovery_record',{}).get('break_cleared'))
        result['flash_command_in_flight']=uart.write_in_flight;result['restore_boot_attempted']=restore_boot_attempted
        if result['uart'].get('reader_error') or not result['containment_confirmed'] or not result['final_domain_guard']:result['status']='FAILED_CONTAINMENT_OR_UART'
        result['serial_recovery']=getattr(uart,'serial_recovery_record',{});result['transport_events']=getattr(host,'transport_events',[])
        result['network_check_failures']=getattr(host,'network_check_failures',0)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))),flush=True)
    return 0 if result['status']=='PASS_F363_PRESERVED_JOURNAL' else 1
def load_plan(path,digest):
    require(c.sha(path)==digest,'plan_hash');plan=json.loads(Path(path).read_text(encoding='ascii'))
    require(plan['schema']=='openmitrastar.f363-install-plan/v1' and plan['status']=='PASS_OFFLINE_REVIEWED_EXECUTOR','plan_scope')
    require(plan['images']==c.images() and plan['store']==c.store_binding(),'image_and_store_contract')
    require(plan['protected']==c.protected_backups() and plan['bootargs']==c.BOOTARGS and plan['known_hosts']==plan['images']['f362']['known_hosts_path'],'scope_contract')
    require(Path(plan['evidence_root']).resolve()==c.EVIDENCE_ROOT.resolve(),'evidence_root_scope')
    for file,h in plan['sources'].items():require(c.sha(file)==h,'source_drift')
    return plan
def main():
    ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args();plan=load_plan(a.plan,a.plan_sha256)
    if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID',hardware_actions=False)));return 0
    require(os.environ.get('OM_F363_CONTEXT') and a.output_dir and a.output_dir.is_dir(),'owning_launcher_required')
    require(a.output_dir.resolve().parent==c.EVIDENCE_ROOT.resolve(),'evidence_directory_scope');return run(plan,a.output_dir)
if __name__=='__main__':raise SystemExit(main())
