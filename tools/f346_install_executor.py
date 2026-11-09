"""F340 install with the verified TFTP/UART primitives and F321 write protocol.

Import/default CLI are file-only. Explicit execution requires the parent-owned
F346 lease/nonce context. Only the mtd4 prefix can be erased or programmed.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys,time
import f346_install_contract as c
import f346_powershell as desktop_ps
import f336_wdt_ram_executor as base
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
        super().__init__({'kernel':plan['images']['f340'],'bootargs':plan['bootargs']},guard,out)
        self.allowed=vocabulary(plan);self.write_in_flight=False;self.erase_requested=False;self.write_requested=False;self._images=plan['images'];self._write_commands=set();self._writer_enabled=False;self._cycle_erased=False;self._cycle_written=False
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
        return json.loads(os.environ.get('OM_F346_CONTEXT','{}')).get('initial_boot_id')==identity['boot_id']
    def _guard(self,network):
        for path,digest in self.plan['sources'].items():require(c.sha(path)==digest,'source_drift')
        argv=[desktop_ps.executable(),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(c.ROOT/'tools/assert_f346_context.ps1')]
        if network:argv.append('-CheckNetwork')
        p=subprocess.run(argv,env=desktop_ps.environment(),capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return p.returncode==0 and p.stdout.strip()==b'PASS_F346_INSTALL_CONTEXT' and not p.stderr
    def guard(self):return self._guard(False)
    def network_guard(self):
        passed=self._guard(True)
        if not passed:self.network_check_failures+=1
        return passed
    def ssh(self,command,data=b'',timeout=20,allow_disconnect=False):
        require(self.network_guard(),'network_guard')
        return super().ssh(command,data,timeout,allow_disconnect)
    def backup_reference(self):
        image=self.plan['images']['f321'];data=Path(image['path']).read_bytes();require(hashlib.sha256(data).hexdigest()==image['sha256'],'backup_image_hash')
        private=c.DEVICE.parent/'analysis'/('f346-private-backup-'+self.out.name);private.mkdir(parents=True,exist_ok=False);restrict_acl(private,directory=True)
        path=private/'backup-reference-f321.webformat.bin'
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
    identity=host.wait_identity(name,uart,start);require(identity['boot_id']!=previous_boot,'boot_not_new');return identity

def run(plan,out,host_factory=Host,uart_factory=Uart,server_factory=ScopedTftpProcess):
    host=host_factory(plan,out);uart=uart_factory(plan,host.guard,out)
    result=dict(schema='openmitrastar.f346-install-result/v1',status='FAILED',stage='baseline',target='mtd4/linux_live',erase_bytes=c.PREFIX,radio_tests_performed=False,watchdog_arm_requested=False,rollback_attempted=False)
    original=None;store_crc=None;reboot_started=False;restore_boot_attempted=False
    def checkpoint(stage):
        result['stage']=stage
        with (out/'events.jsonl').open('a',encoding='ascii') as stream:stream.write(json.dumps(dict(stage=stage,monotonic_ms=round(time.monotonic()*1000)))+'\n')
    try:
        require(host.guard(),'lease');original=host.identity('f321');require(host.initial_binding(original),'initial_nonce_boot_mismatch');result['baseline']=original
        result['rollback_reference']=host.backup_reference()
        uart.open();reboot_started=True;checkpoint('bootbase-preflight');host.reboot_to_prompt(uart)
        base.inactive_hardware(uart);selector(uart);result['protected_before']=protected(uart,plan)
        store_crc=flash_crc(uart,c.STORE,c.STORE_BYTES,plan['erased_store_crc32']);result['store_crc32']=store_crc
        result['current_f321_crc32']=flash_crc(uart,c.LIVE,c.SLOT,plan['images']['f321']['full_slot_crc32'])
        checkpoint('install-f340');result['writer']=write_image(uart,host,plan,plan['images']['f340'],out/'install',store_crc,server_factory)
        checkpoint('boot-f340');result['f340_identity']=boot_written(uart,host,plan,'f340',original['boot_id'])
        checkpoint('platform-f340');result['platform']=host.platform('f340',out/'platform-f340');result['watchdog']=host.watchdog_inactive()
        result['status']='PASS_F340_PERSISTENT_WATCHDOG_BASELINE';checkpoint('complete-f340-kept')
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
                    result['rollback_attempted']=True;checkpoint('restore-f321')
                    result['restore_writer']=write_image(uart,host,plan,plan['images']['f321'],out/'restore',store_crc,server_factory)
                else:base.inactive_hardware(uart)
                checkpoint('boot-f321-return');restore_boot_attempted=True
                result['returned_identity']=boot_written(uart,host,plan,'f321',original['boot_id'],prefix_only=not mutated);result['return_platform']=host.platform('f321',out/'platform-f321')
                result['status']='FAILED_F340_WITH_EXACT_F321_RETURN';checkpoint('complete-f321-returned')
            except Exception as recovery:
                result['recovery_error']=str(recovery) if isinstance(recovery,Failure) else type(recovery).__name__
                result['status']='FAILED_RECOVERY_UNPROVEN_NO_RETRY'
        elif reboot_started:result['status']='STOP_UNCERTAIN_NO_AUTOMATIC_WRITE'
    finally:
        try:result['children_contained']=host.contain()
        except Exception:result['children_contained']=False
        try:result['uart']=uart.close()
        except Exception:result['uart']={}
        result['containment_confirmed']=result['children_contained'] and result['uart'].get('reader_stopped') is True and result['uart'].get('port_closed') is True
        try:result['final_domain_guard']=host.guard() is True
        except Exception:result['final_domain_guard']=False
        result['retain_lease_required']=not result['containment_confirmed'] or uart.write_in_flight or not result['final_domain_guard']
        result['flash_command_in_flight']=uart.write_in_flight;result['restore_boot_attempted']=restore_boot_attempted
        if result['uart'].get('reader_error') or not result['containment_confirmed'] or not result['final_domain_guard']:result['status']='FAILED_CONTAINMENT_OR_UART'
        result['transport_events']=getattr(host,'transport_events',[])
        result['network_check_failures']=getattr(host,'network_check_failures',0)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps(dict(status=result['status'],result=str(out/'result.json'))),flush=True)
    return 0 if result['status']=='PASS_F340_PERSISTENT_WATCHDOG_BASELINE' else 1
def load_plan(path,digest):
    require(c.sha(path)==digest,'plan_hash');plan=json.loads(Path(path).read_text(encoding='ascii'))
    require(plan['schema']=='openmitrastar.f346-install-plan/v1' and plan['status']=='PASS_OFFLINE_REVIEWED_EXECUTOR','plan_scope')
    require(plan['images']==c.images(),'image_contract')
    require(plan['protected']==c.protected_backups() and plan['bootargs']==c.BOOTARGS and plan['known_hosts']==plan['images']['f321']['known_hosts_path'],'scope_contract')
    for file,h in plan['sources'].items():require(c.sha(file)==h,'source_drift')
    return plan
def main():
    ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');a=ap.parse_args();plan=load_plan(a.plan,a.plan_sha256)
    if not a.execute:print(json.dumps(dict(status='OFFLINE_VALID',hardware_actions=False)));return 0
    require(os.environ.get('OM_F346_CONTEXT') and a.output_dir and a.output_dir.is_dir(),'owning_launcher_required');return run(plan,a.output_dir)
if __name__=='__main__':raise SystemExit(main())
