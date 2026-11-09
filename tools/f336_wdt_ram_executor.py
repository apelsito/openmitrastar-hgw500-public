"""F336 RAM-only executor. Import/default CLI are offline; explicit --execute only.

Parent launcher owns F319 lease/nonce. Existing serial and scoped TFTP transport
are reused; no flash write/erase or persistent Bootbase environment vocabulary.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,subprocess,sys,threading,time,queue
from f325_ethernet_uart import native_serial_factory
from f325_ethernet_server_process import ScopedTftpProcess
from f325_scoped_tftp import load_verified_file
from f325_ethernet_ram_gate import verify_iminfo,verify_silent,verify_environment,response_lines,verify_transfer
from f336_wdt_ram_plan import watchdog_inactive,evaluate

ROOT=Path(__file__).resolve().parents[1]
PROMPT=re.compile(rb'(?:^|[\r\n])topaz>[ \t]*$')
class Failure(RuntimeError):pass
def require(value,code):
    if not value:raise Failure(code)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load_plan(path,digest):
    require(sha(path)==digest,'plan_hash');p=json.loads(Path(path).read_text())
    require(p['schema']=='openmitrastar.f336-executor/v1' and p['status']=='REVIEWED_OFFLINE_READY' and p['flash_allowed'] is False,'plan_scope')
    for name,value in p['sources'].items():require(sha(name)==value,'source_hash')
    for value in (p['kernel'],p['probe']):require(sha(value['path'])==value['sha256'] and Path(value['path']).stat().st_size==value['bytes'],'artifact_hash')
    audit_path=p['startup_write_audit']['path'];require(sha(audit_path)==p['startup_write_audit']['sha256'],'startup_audit_hash')
    audit=json.loads(Path(audit_path).read_text())
    require(audit['schema']=='openmitrastar.f337-f321-startup-storage-audit/v1' and audit['status']=='PASS_OFFLINE_DEFAULT_STARTUP_STORAGE_AUDIT' and audit['all_dtb_mtd_views_rom'] is True and audit['automatic_store_commit_found'] is False,'startup_write_audit_required')
    return p
def vocabulary(plan):
    return frozenset(['setenv ipaddr 192.168.1.90','setenv serverip 192.168.1.49','printenv ipaddr','printenv serverip','printenv bootargs','printenv filesize',
        'md.l 0xe0000004 1','md.l 0xf4000000 1','md.l 0xf4000008 1','md.l 0x84000000 1','iminfo 0x83000000',
        'spi_flash read 0x007e0000 0x83000000 0x007a0000','crc32 0x83000000 0x00517000 0x84000000','crc32 0x83000000 0x007a0000 0x84000000',
        f"tftpboot 0x83000000 {Path(plan['kernel']['path']).name}",f"crc32 0x83000000 0x{plan['kernel']['bytes']:08x} 0x84000000",
        'setenv bootargs '+plan['bootargs'],'bootm 0x83000000'])
def redact(line):
    text=line.decode('ascii','replace')
    if re.search(r'(?i)(?:password|passwd|passphrase|psk|credential|ap_pin|wps.pin|private.key|runtime.conf|settings.conf|key=|calibration)',text):return '[sensitive-line-redacted]'
    text=re.sub(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}','[mac-redacted]',text)
    if not re.search(r'(?:topaz>|ZHAL>|Bootbase Version|U-Boot |Linux version |Hit any key|Verifying Checksum|Checking Image|Image Name:|Image Type:|Data Size:|Load Address:|Entry Point:|Bytes transferred|Starting kernel|Kernel panic|Oops:|BUG:|Misaligned Access|Fatal exception|^[ef]400000[08]:|^e0000004:|^84000000:)',text):return '[unclassified-line-redacted]'
    return ''.join(c if c in '\t' or 32<=ord(c)<127 else '?' for c in text)
def word(response,address):
    hits=re.findall(rb'(?:^|[\r\n])'+f'{address:08x}'.encode()+rb':[ \t]+([0-9a-fA-F]{8})(?:[ \t]|[\r\n]|$)',response)
    require(len(hits)==1,'register_word_cardinality');return int(hits[0],16)

class Capture:
    """A single reader remains alive across boot, probe, reset and return."""
    def __init__(self,plan,guard,out,serial_factory=native_serial_factory):
        self.plan=plan;self.guard=guard;self.out=out;self.factory=serial_factory;self.serial=None
        self.lock=threading.Lock();self.stop=threading.Event();self.buffer=bytearray();self.total=0;self.sequence=0;self.failed=None;self.thread=None;self.prompt_ready=False;self.prompt_floor=0
        self.hash=hashlib.sha256();self.allowed=vocabulary(plan);self.autoboot=False;self.auto_until=0;self.auto_seen=set();self.auto_count=0;self.auto_floor=0;self.error_type=None;self.reset_times=[];self.fatal=False
    def stop_autoboot(self,seconds):
        require(0<seconds<=120,'autoboot_deadline');self.auto_floor=self.checkpoint();self.autoboot=True;self.auto_until=time.monotonic()+seconds;self.auto_seen.clear();self.auto_count=0
    def open(self):
        require(self.guard(),'lease');self.serial=self.factory();require(not self.serial.is_open,'serial_already_open')
        self.serial.port='COM3';self.serial.dtr=False;self.serial.rts=False;self.serial.open();require(self.serial.is_open,'serial_open')
        self.thread=threading.Thread(target=self._read,name='F336-UART-RX',daemon=True);self.thread.start()
    def _read(self):
        pending=bytearray()
        try:
            with (self.out/'uart-redacted.jsonl').open('x',encoding='ascii') as log:
                while not self.stop.is_set():
                    data=self.serial.read(max(1,min(getattr(self.serial,'in_waiting',0),4096)))
                    if not data:continue
                    now=time.monotonic();self.hash.update(data)
                    with self.lock:
                        self.total+=len(data);self.buffer.extend(data)
                        if len(self.buffer)>262144:del self.buffer[:-262144]
                    pending.extend(data)
                    while b'\n' in pending:
                        line,_,pending=pending.partition(b'\n');self.sequence+=1
                        if line.strip(b'\0\r \t')==b'Boot reached stage 13' or re.match(rb'(?:U-Boot |Bootbase Version)',line.strip()):self.reset_times.append(now)
                        log.write(json.dumps(dict(seq=self.sequence,host_ms=round(now*1000),bytes=len(line)+1,text=redact(line.rstrip(b'\r'))))+'\n');log.flush()
                    if len(pending)>4096:
                        self.sequence+=1;log.write(json.dumps(dict(seq=self.sequence,host_ms=round(now*1000),bytes=len(pending),text='[oversized-unterminated-line-redacted]'))+'\n');log.flush();pending.clear()
                    tail=self.tail()
                    if self.total>self.prompt_floor and PROMPT.search(tail):self.prompt_ready=True
                    if re.search(rb'Kernel panic|Oops:|BUG:|Misaligned Access|Fatal exception',tail[-8192:]):self.fatal=True
                    if self.autoboot and now>self.auto_until:self.autoboot=False
                    if self.autoboot:
                        for match in re.finditer(rb'Hit any key|(?:^|[\r\n])ZHAL>\s*$',tail):
                            token=match.group();offset=token.find(b'ZHAL>') if b'ZHAL>' in token else 0
                            position=self.total-len(tail)+match.start()+offset
                            if position<self.auto_floor:continue
                            if position in self.auto_seen:continue
                            self.auto_seen.add(position);self.auto_count+=1;require(self.auto_count<=4,'autoboot_events_exceeded')
                            self.serial.write(b' \r' if b'Hit any key' in match.group() else b'\x15\x08ATGU\r')
                if pending:
                    self.sequence+=1;log.write(json.dumps(dict(seq=self.sequence,host_ms=round(time.monotonic()*1000),bytes=len(pending),text=redact(pending)))+'\n')
        except Exception as error:
            self.error_type=type(error).__name__
            self.failed=str(error) if isinstance(error,Failure) and re.fullmatch('[a-z0-9_]{1,64}',str(error)) else 'uart_reader_failed'
    def tail(self):
        with self.lock:return bytes(self.buffer)
    def checkpoint(self):
        with self.lock:return self.total
    def has_prompt(self):return self.prompt_ready and bool(PROMPT.search(self.tail()))
    def invalidate_prompt(self):self.prompt_floor=self.checkpoint();self.prompt_ready=False
    def since(self,start):
        with self.lock:
            require(self.total-start<=len(self.buffer),'uart_window_overflow');return bytes(self.buffer[-(self.total-start):]) if self.total>start else b''
    def wait_prompt(self,timeout,start=None):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            require(not self.failed,'uart_reader_failed');data=self.since(start) if start is not None else self.tail()
            if self.has_prompt() and PROMPT.search(data):self.autoboot=False;return data
            time.sleep(.02)
        raise Failure('topaz_prompt_timeout')
    def command(self,text,timeout=15,handoff=False):
        require(text in self.allowed,'command_not_allowlisted');require(self.guard(),'lease');require(not self.failed,'uart_reader_failed')
        require(self.has_prompt(),'topaz_prompt_missing');start=self.checkpoint();self.invalidate_prompt()
        raw=text.encode('ascii')+b'\r';require(self.serial.write(raw)==len(raw),'uart_short_write')
        if handoff:return start
        return self.wait_prompt(timeout,start)
    def close(self):
        self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        alive=bool(self.thread and self.thread.is_alive())
        if self.serial and self.serial.is_open:self.serial.close()
        require(not alive,'uart_reader_not_contained')
        return dict(bytes=self.total,sha256=self.hash.hexdigest(),sequence_lines=self.sequence,reader_error=self.failed,reader_error_type=self.error_type,raw_saved=False,reader_stopped=True,port_closed=True)

class Host:
    def __init__(self,plan,out):self.plan=plan;self.out=out;self.children=[];self.threads=[];self.transport_events=[]
    def guard(self):
        for path,digest in self.plan['sources'].items():require(sha(path)==digest,'source_drift')
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/f336_assert_context.ps1')],capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return p.returncode==0 and p.stdout.strip()==b'PASS_F336_RAM_CONTEXT' and not p.stderr
    def ssh_argv(self,command):
        return [str(Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'),'-i',str(Path.home()/'.ssh/id_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+self.plan['known_hosts'],'-o','LogLevel=ERROR','root@192.168.1.90',command]
    def ssh(self,command,data=b'',timeout=20,allow_disconnect=False):
        require(not allow_disconnect or command=='echo b >/proc/sysrq-trigger','disconnect_scope')
        p=subprocess.Popen(self.ssh_argv(command),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.children.append(p)
        try:out,err=p.communicate(data,timeout=timeout)
        except subprocess.TimeoutExpired:
            if p.poll() is None:p.kill()
            try:out,err=p.communicate(timeout=3)
            except subprocess.TimeoutExpired:raise Failure('ssh_containment_unproven') from None
            require(p.poll() is not None,'ssh_containment_unproven')
            if not allow_disconnect:raise Failure('ssh_deadline')
            self.transport_events.append(dict(event='reboot_ssh_timeout_contained',reboot_proven=False,fresh_uart_prompt_required=True))
        require(len(out)<=65536 and len(err)<=65536,'ssh_output_limit')
        if not allow_disconnect:require(p.returncode==0 and not err,'ssh_failed')
        return out
    def identity(self,ram):
        script="printf 'boot_id='; cat /proc/sys/kernel/random/boot_id; printf 'uts='; uname -v; printf 'marker='; if [ -r /proc/device-tree/openmitrastar,f336-wdt-ram ]; then cat /proc/device-tree/openmitrastar,f336-wdt-ram; fi; printf '\\n'; grep -qx 'OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.8.5-f321-classic-ui-f314-device' /etc/openmitrastar/release"
        rows=dict(x.split('=',1) for x in self.ssh(script).decode('ascii').splitlines() if '=' in x)
        rows['marker']=rows.get('marker','').removesuffix('\0');require('\0' not in rows['marker'],'marker_encoding')
        require(re.fullmatch('[0-9a-f-]{36}',rows.get('boot_id','')),'boot_identity')
        require((rows.get('marker')=='F336_WDT_RAM_ONLY' and '#336' in rows.get('uts','')) if ram else (rows.get('marker')=='' and '#336' not in rows.get('uts','')),'kernel_identity')
        return rows
    def wait_identity(self,ram,timeout=120):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:return self.identity(ram)
            except (Failure,UnicodeError,ValueError):time.sleep(1)
        raise Failure('ssh_boot_identity_timeout')
    def put_probe(self):
        self.ssh('umask 077; mkdir -p /run/openmitrastar/f336; cat >/run/openmitrastar/f336/wdt-probe; chmod 700 /run/openmitrastar/f336/wdt-probe',Path(self.plan['probe']['path']).read_bytes())
        answer=self.ssh('sha256sum /run/openmitrastar/f336/wdt-probe').split()
        require(answer and answer[0].decode()==self.plan['probe']['sha256'],'remote_probe_hash')
    def inspect(self):
        data=json.loads(self.ssh('/run/openmitrastar/f336/wdt-probe --inspect'))
        require(data.get('event')=='inspect' and data.get('ready_for_arm')==1 and data.get('device_opened')==0,'inspect_not_unarmed_ready');return data
    def storage_gate(self):
        raw=self.ssh("cat /proc/cmdline; printf '\\nF336_MOUNTS\\n'; cat /proc/mounts; printf 'F336_FLAGS\\n'; for d in /sys/class/mtd/mtd*/flags; do [ -r \"$d\" ] && cat \"$d\"; done")
        commandline,rest=raw.split(b'\nF336_MOUNTS\n',1);mounts,flags=rest.split(b'F336_FLAGS\n',1)
        require(b'openmitrastar.persist=rw' not in commandline,'persistence_rw_cmdline')
        persist=False
        for row in mounts.splitlines():
            values=row.split()
            if len(values)<4:continue
            if values[1]==b'/persist':persist=True;require(b'ro' in values[3].split(b','),'persist_not_readonly')
            require(b'lyoko_store' not in values[0] and b'store' not in values[1].lower(),'store_mounted')
        values=[int(x,0) for x in flags.decode('ascii').splitlines() if x]
        require(persist and len(values)>=5 and all(not x&0x400 for x in values),'writable_mtd_or_missing_views')
        return dict(persist_readonly=True,store_mounted=False,mtd_views=len(values),mtd_writable=False,raw_output_saved=False)
    def reboot_to_prompt(self,uart,software_recovery=False):
        require(self.guard(),'lease');uart.stop_autoboot(120);start=uart.checkpoint();uart.invalidate_prompt()
        self.ssh("echo b >/proc/sysrq-trigger",timeout=12,allow_disconnect=True)
        uart.wait_prompt(120,start)
    def contain(self):
        for p in self.children:
            if p.poll() is None:p.terminate()
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
        for t in self.threads:t.join(timeout=2)
        return all(p.poll() is not None for p in self.children) and all(not t.is_alive() for t in self.threads)

def inactive_hardware(uart):
    mapping=word(uart.command('md.l 0xe0000004 1'),0xe0000004)
    require(not mapping&((1<<29)|(1<<30)),'legacy_map_unproven')
    controls=[];counters=[]
    for i in range(2):
        controls.append(word(uart.command('md.l 0xf4000000 1'),0xf4000000));counters.append(word(uart.command('md.l 0xf4000008 1'),0xf4000008))
        if not i:time.sleep(.2)
    record=dict(source='bootbase-owned-uart',map_value=mapping,controls=controls,counters=counters,same_target_and_lease=True,fresh=True)
    require(watchdog_inactive(record)['watchdog_inactive_observed'],'watchdog_not_inactive');return record
def flash_snapshot(uart,expected_full=None):
    command='spi_flash read 0x007e0000 0x83000000 0x007a0000';response=uart.command(command,timeout=120)
    require(response_lines(response,command)==['Read: flash=0x7e0000 mem=0x83000000 size=7995392 ret_size=7995392'],'spi_read_unconfirmed')
    uart.command('crc32 0x83000000 0x00517000 0x84000000');prefix=word(uart.command('md.l 0x84000000 1'),0x84000000)
    require(prefix==0xbd1135df,'f321_prefix_crc')
    uart.command('crc32 0x83000000 0x007a0000 0x84000000');full=word(uart.command('md.l 0x84000000 1'),0x84000000)
    if expected_full is not None:require(full==expected_full,'flash_changed_during_ram_probe')
    return full
def iminfo(uart):
    data=uart.command('iminfo 0x83000000')
    verify_iminfo(data,'iminfo 0x83000000')
    require(re.search(rb'Load Address:\s*(?:0x)?8493a000',data,re.I) and re.search(rb'Entry Point:\s*(?:0x)?8493e000',data,re.I),'image_entry_load')
def environment(uart,name,value):
    command=f'setenv {name} {value}';verify_silent(uart.command(command),command)
    command='printenv '+name;verify_environment(uart.command(command),command,name,value)
def experiment(host,uart,events):
    require(host.guard(),'lease');p=subprocess.Popen(host.ssh_argv('exec /run/openmitrastar/f336/wdt-probe --session'),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));host.children.append(p)
    rows=queue.Queue();errors=[]
    def read():
        try:
            for raw in iter(p.stdout.readline,b''):
                require(len(raw)<=2048,'probe_line_limit');row=json.loads(raw);row['host_ms']=round(time.monotonic()*1000);rows.put(row)
        except Exception:errors.append('probe_output_invalid')
    thread=threading.Thread(target=read,daemon=True);host.threads.append(thread);thread.start()
    def next_event(name,timeout):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            require(not errors,'probe_output_invalid')
            try:row=rows.get(timeout=.1)
            except queue.Empty:continue
            events.append(row)
            require(row.get('event') not in ('verdict','close_after_verdict'),'probe_negative_verdict')
            if row.get('event')==name:return row
        raise Failure('probe_event_deadline')
    def send(line):
        p.stdin.write(line.encode()+b'\n');p.stdin.flush()
    reset=None
    try:
        next_event('ready',5);send('ARM');next_event('armed',5)
        tx=ack=None
        for _ in range(24):
            time.sleep(1);tx=round(time.monotonic()*1000);send('PET');ack=next_event('pet',3)['host_ms']
        send('CEASE');next_event('cease',3);uart.stop_autoboot(100);start=uart.checkpoint();deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            require(not errors,'probe_output_invalid');require(not uart.failed,'uart_reader_failed')
            while not rows.empty():
                row=rows.get();events.append(row)
                require(row.get('event') not in ('verdict','close_after_verdict'),'probe_negative_verdict')
                if row.get('event')=='sample':require(row.get('unexplained_counter_increases')==0,'foreign_pet_observed')
            newer=[t for t in uart.reset_times if t*1000>ack]
            if newer:reset=round(newer[0]*1000);break
            time.sleep(.02)
        require(reset is not None,'watchdog_no_reset')
        uart.wait_prompt(60,start)
        return dict(last_pet_host_send_ms=tx,last_pet_host_ack_ms=ack,uart_reset_host_ms=reset,uart_reset_observed=True)
    finally:
        if reset is None and p.poll() is None:
            events.append(dict(event='controller_negative_verdict',result='EXPERIMENT_NOT_ACCEPTED'))
            try:
                send('ABORT');end=time.monotonic()+3
                while time.monotonic()<end:
                    try:row=rows.get(timeout=.1);events.append(row)
                    except queue.Empty:continue
                    if row.get('event')=='close_after_verdict':break
            except (OSError,ValueError):pass
        if p.stdin:
            try:p.stdin.close()
            except OSError:pass
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=3)
        thread.join(timeout=2);require(not thread.is_alive(),'probe_reader_not_contained')

def run(plan,out,mode):
    host=Host(plan,out);uart=Capture(plan,host.guard,out);server=None;original=None;ram=None;booted=False;reboot_started=False;return_attempted=False;trace=dict(probe_events=[],fallback_reset_requested=False);result=dict(status='INCOMPLETE',flash_write_commands_issued=False,phase='baseline')
    try:
        require(host.guard(),'lease');original=host.identity(False);trace['baseline']=dict(pinned_f321=True,boot_id=original['boot_id'],uts_version=original['uts'])
        uart.open();reboot_started=True;host.reboot_to_prompt(uart);result['preboot_watchdog']=inactive_hardware(uart);before=flash_snapshot(uart);result['flash_crc_before']=f'{before:08x}'
        payload=load_verified_file(Path(plan['kernel']['path']),plan['kernel']['sha256'],plan['kernel']['bytes'])
        server=ScopedTftpProcess(guard=host.guard,output_dir=out/'tftp');server.start(payload,bind='192.168.1.49',client='192.168.1.90',filename=payload.source_path.name)
        environment(uart,'ipaddr','192.168.1.90');environment(uart,'serverip','192.168.1.49')
        response=uart.command('tftpboot 0x83000000 '+payload.source_path.name,timeout=300)
        verify_transfer(response,'tftpboot 0x83000000 '+payload.source_path.name,payload.expected_bytes)
        result['tftp']=server.finish();require(server.close(),'server_not_contained');server=None
        uart.command(f'crc32 0x83000000 0x{payload.expected_bytes:08x} 0x84000000')
        require(word(uart.command('md.l 0x84000000 1'),0x84000000)==int(plan['kernel']['crc32'],16),'ram_crc')
        iminfo(uart);inactive_hardware(uart)
        environment(uart,'bootargs',plan['bootargs']);uart.command('bootm 0x83000000',handoff=True);booted=True
        ram=host.wait_identity(True);require(ram['boot_id']!=original['boot_id'],'ram_boot_not_new');result['storage_gate']=host.storage_gate();host.put_probe();result['inspect']=host.inspect();result['phase']='unarmed-inspection-complete'
        trace['ram']=dict(dt_marker=ram['marker'],uts_version=ram['uts'],uart_bound=True,boot_id=ram['boot_id'])
        print(json.dumps(dict(event='F336_RAM_INSPECT_PASS',watchdog_opened=False,boot_id=ram['boot_id'],next='ARM or RETURN on stdin' if mode=='experiment' else 'return F321')),flush=True)
        do_arm=False
        if mode=='experiment':
            reply=queue.Queue();threading.Thread(target=lambda:reply.put(sys.stdin.readline()),daemon=True).start()
            try:command=reply.get(timeout=120).strip()
            except queue.Empty:command='RETURN'
            require(command in ('ARM','RETURN',''),'phase_command');do_arm=command=='ARM'
        if do_arm:
            current=host.identity(True);require(current['boot_id']==ram['boot_id'],'ram_session_changed');host.storage_gate();host.inspect();result['phase']='watchdog-experiment'
            trace.update(experiment(host,uart,trace['probe_events']))
        else:host.reboot_to_prompt(uart)
        result['post_reset_watchdog']=inactive_hardware(uart);trace['post_reset_watchdog']=result['post_reset_watchdog']
        after=flash_snapshot(uart,before);result['flash_crc_after']=f'{after:08x}';iminfo(uart)
        environment(uart,'bootargs',plan['bootargs']);return_attempted=True;uart.command('bootm 0x83000000',handoff=True)
        returned=host.wait_identity(False);require(returned['boot_id']!=ram['boot_id'] and returned['uts']==original['uts'],'flash_return_identity')
        trace['return']=dict(pinned_f321=True,dt_marker_present=False,uts_version=returned['uts'],boot_id=returned['boot_id']);trace['fatal_or_panic_marker']=uart.fatal
        result['trace']=trace;result['evaluation']=evaluate(trace) if do_arm else None
        result['status']=result['evaluation']['status'] if do_arm else 'PASS_RAM_INSPECT_AND_F321_RETURN'
    except Exception as e:
        result['status']='FAILED';result['error']=str(e) if isinstance(e,Failure) else type(e).__name__
        # A failed test remains failed even if recovery succeeds. No repeated arm.
        result['trace']=trace
        if reboot_started and original is not None and not return_attempted:
            try:
                require(host.contain(),'prior_helpers_not_contained')
                if server:require(server.close(),'tftp_not_contained');server=None
                if not uart.has_prompt():trace['fallback_reset_requested']=True;host.reboot_to_prompt(uart,software_recovery=True)
                inactive_hardware(uart)
                flash_snapshot(uart,result.get('flash_crc_before') and int(result['flash_crc_before'],16));iminfo(uart)
                environment(uart,'bootargs',plan['bootargs']);return_attempted=True;uart.command('bootm 0x83000000',handoff=True)
                recovered=host.wait_identity(False);require(recovered['uts']==original['uts'] and recovered['boot_id']!=(ram or original)['boot_id'],'recovery_identity');result['software_recovery']='F321_RETURNED_NOT_WDT_PASS'
            except Exception as recovery:result['software_recovery']='UNPROVEN_'+(str(recovery) if isinstance(recovery,Failure) else type(recovery).__name__)
    finally:
        if server:
            try:result['server_containment']=server.close()
            except Exception:result['server_containment']=False
        try:result['ssh_children_stopped']=host.contain()
        except Exception:result['ssh_children_stopped']=False
        if not result['ssh_children_stopped'] or result.get('server_containment') is False:result['status']='FAILED_CONTAINMENT'
        try:result['uart_capture']=uart.close()
        except Exception:result['uart_capture']={'containment':False};result['status']='FAILED_CONTAINMENT'
        result['containment_confirmed']=result['ssh_children_stopped'] and result.get('server_containment') is not False and result.get('uart_capture',{}).get('reader_stopped') is True and result.get('uart_capture',{}).get('port_closed') is True
        result['transport_events']=getattr(host,'transport_events',[])
        if result.get('uart_capture',{}).get('reader_error'):result['status']='FAILED_UART_CAPTURE'
        if not result['containment_confirmed']:result['status']='FAILED_CONTAINMENT'
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'result':str(out/'result.json'),'status':result['status']}),flush=True)
    return 0 if result['status'] in ('PASS_RAM_INSPECT_AND_F321_RETURN','CESSATION_RESET_AND_F321_RETURN_OBSERVED') else 1
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True);ap.add_argument('--output-dir',type=Path);ap.add_argument('--execute',action='store_true');ap.add_argument('--mode',choices=['inspect','experiment'],default='inspect');args=ap.parse_args();plan=load_plan(args.plan,args.plan_sha256)
    if not args.execute:print(json.dumps(dict(status='OFFLINE_PLAN_VALID',hardware_actions=False)));return 0
    require(args.output_dir and args.output_dir.is_dir(),'parent_output_required');require(os.environ.get('OM_F336_RAM_CONTEXT'),'parent_context_required')
    return run(plan,args.output_dir,args.mode)
if __name__=='__main__':raise SystemExit(main())
