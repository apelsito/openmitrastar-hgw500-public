"""Run the actual F346 pipeline against an in-memory flash/UART/host model."""
from pathlib import Path
from unittest.mock import patch
import argparse,copy,hashlib,json,tempfile,unittest
import f361_install_executor as x
import f361_install_contract as c

def reply(command,*rows):return (command+'\r\n'+'\r\n'.join(rows)+'\r\ntopaz> ').encode()
class Model:
    def __init__(self,plan,scenario):
        self.plan=plan;self.scenario=scenario;self.images={n:Path(v['path']).read_bytes() for n,v in plan['images'].items()}
        self.flash=bytearray(self.images['f358']+b'\xff'*(c.PREFIX-len(self.images['f358']))+Path(plan['store']['path']).read_bytes())
        self.parts={(v['offset'],v['bytes']):Path(v['path']).read_bytes() for v in plan['protected']['parts']}
        self.ram={};self.commands=[];self.events=[];self.writes=0;self.erases=0;self.boots=[];self.image='f358';self.boot_id='initial';self.ready=False;self.crc=0;self.fail_used=False
        if scenario=='store_not_erased':self.flash[c.PREFIX+7]=0
class FakeHost:
    model=None
    def __init__(self,plan,out):self.plan=plan;self.out=out;self.s=self.model;self.servers=[];self.transport_events=[]
    def guard(self):return self.s.scenario!='no_lease'
    def network_guard(self):
        if self.s.scenario=='network_drifts_after_erase' and self.s.erases:
            self.s.events.append('network-rejected');return False
        return True
    def backup_reference(self):
        self.s.events.append('private-backup-reference')
        return dict(path='synthetic-backup-receipt-no-file',sha256=self.plan['images']['f358']['sha256'],fresh_physical_dump=False,private_acl_applied=True)
    def initial_binding(self,identity):return self.s.scenario!='nonce_boot_changed'
    def identity(self,name):
        if name!=self.s.image:raise x.Failure('kernel_identity')
        return dict(boot_id=self.s.boot_id,uts=self.plan['images'][name]['kernel_build'],f340=self.plan['images'][name]['marker'],f336='')
    def wait_identity(self,name,uart,start,timeout=180):
        if uart.has_prompt():raise x.Failure('bootm_returned_no_retry')
        if not self.network_guard():raise x.Failure('network_guard')
        return self.identity(name)
    def reboot_to_prompt(self,uart,software_recovery=False):
        if not self.network_guard():raise x.Failure('network_guard')
        self.s.events.append('reboot');self.s.ready=True
    def platform(self,name,out):
        self.s.events.append('platform-'+name)
        if name=='f361' and self.s.scenario in ('platform_fails','rollback_bootm_returns','rollback_write_fails','containment_fails'):raise x.Failure('platform_gate')
        return dict(status='PASS',checks=27)
    def verify_store(self):
        actual=hashlib.sha256(bytes(self.s.flash[c.PREFIX:])).hexdigest()
        x.require(actual==self.plan['store']['sha256'],'model_store_drift')
        return dict(sha256=actual,read_only_mtd=True)
    def verify_configuration(self):
        return dict(source='journal',sequence=1)
    def watchdog_inactive(self):
        if self.s.scenario=='wdt_unexpectedly_armed':raise x.Failure('watchdog_not_inactive')
        return dict(event='inspect',ready_for_arm=1,device_opened=0,control_valid=1,control='00000000')
    def contain(self):
        self.s.events.append('contain')
        return all(server.close() for server in self.servers) and self.s.scenario!='containment_fails'
class FakeServer:
    def __init__(self,**kw):self.s=FakeHost.model;self.closed=False
    def start(self,payload,**kw):
        self.s.pending=payload.data;self.s.pending_name=payload.source_path.name;self.s.events.append('server-start')
    def finish(self):return dict(status='PASS_TFTP_SINGLE_TRANSFER',sockets_closed=True)
    def close(self):
        if self.s.scenario=='server_uncontained':return False
        self.closed=True;self.s.events.append('server-close');return True
class FakeUart:
    def __init__(self,plan,guard,out):
        self.s=FakeHost.model;self.plan=plan;self.guard=guard;self.allowed=x.vocabulary(plan);self._images=plan['images'];self._write_commands=set();self.write_in_flight=False;self.erase_requested=False;self.write_requested=False;self.failed=None;self._writer_enabled=False;self._cycle_erased=False;self._cycle_written=False
    def open(self):self.s.events.append('serial-open')
    def close(self):return dict(reader_stopped=True,port_closed=True,reader_error=None)
    def has_prompt(self):return self.s.ready
    def enable_writer(self,image):return x.Uart.enable_writer(self,image)
    def disable_writer(self):return x.Uart.disable_writer(self)
    def mutate(self,command):return x.Uart.mutate(self,command)
    def command(self,cmd,timeout=15,handoff=False):
        x.require(self.s.ready,'topaz_prompt_missing');x.require(cmd in self.allowed,'not_allowlisted');x.require(self.guard(),'lease');self.s.commands.append(cmd);self.s.ready=False
        args=cmd.split();rows=[]
        if args[0]=='setenv':self.s.env=getattr(self.s,'env',{});self.s.env[args[1]]=' '.join(args[2:])
        elif args[0]=='printenv':
            name=args[1];values={'bootcmd':'bootselect','bootselect':'1' if self.s.scenario=='selector_changed' else '0','filesize':hex(len(self.s.ram.get(c.LOAD,b'')))};values.update(getattr(self.s,'env',{}));rows=[name+'='+values[name]]
        elif args[0]=='tftpboot':
            self.s.ram[c.LOAD]=self.s.pending
            if self.s.scenario=='bad_ram_transfer' and not self.s.fail_used:self.s.ram[c.LOAD]=bytes([self.s.pending[0]^1])+self.s.pending[1:];self.s.fail_used=True
            rows=[f'Bytes transferred = {len(self.s.pending)} (0x{len(self.s.pending):x})']
        elif args[0]=='md.l':
            address=int(args[1],16);value=self.s.crc if address==c.SCRATCH else 0x32af if address==0xe0000004 else 0xffff if address==0xf4000008 else 0
            if address==0xf4000000 and self.s.scenario=='wdt_persists_in_bootbase':value=1
            rows=[f'{address:08x}: {value:08x}']
        elif args[0]=='crc32':
            address,n=int(args[1],16),int(args[2],16);self.s.crc=int(c.crc(self.s.ram[address][:n]),16)
        elif args[0]=='iminfo':rows=['## Checking Image at 83000000 ...','Load Address: 8493a000','Entry Point: 8493e000','   Verifying Checksum ... OK']
        elif args[:2]==['spi_flash','read']:
            offset,address,n=map(lambda v:int(v,16),args[2:]);data=self.s.parts.get((offset,n))
            if data is None:x.require(c.LIVE<=offset and offset+n<=c.LIVE+c.SLOT,'read_scope');data=bytes(self.s.flash[offset-c.LIVE:offset-c.LIVE+n])
            if self.s.scenario=='protected_changed' and offset==0x20000:data=bytes([data[0]^1])+data[1:]
            self.s.ram[address]=data;rows=[f'Read: flash=0x{offset:x} mem=0x{address:x} size={n} ret_size={n}']
        elif args[:2]==['spi_flash','erase']:
            offset,n=int(args[2],16),int(args[3],16);x.require(offset==c.LIVE and n==c.PREFIX,'erase_scope');self.s.erases+=1;self.s.events.append('erase')
            self.s.flash[:n]=b'\xff'*n
            if self.s.scenario=='incomplete_erase' and not self.s.fail_used:self.s.flash[0]=0;self.s.fail_used=True
            rows=[f'Erase: flash=0x{offset:x} size={n}']
        elif args[:2]==['spi_flash','write']:
            offset,address,n=map(lambda v:int(v,16),args[2:]);x.require(offset==c.LIVE and n<c.PREFIX,'write_scope');self.s.writes+=1;self.s.events.append('write')
            if self.s.scenario=='write_timeout' and not self.s.fail_used:self.s.fail_used=True;raise x.Failure('uart_deadline_expired')
            self.s.flash[:n]=self.s.ram[address][:n]
            actual=n
            if (self.s.scenario=='bad_write_ack' and self.s.writes==1) or (self.s.scenario=='rollback_write_fails' and self.s.writes==2):actual=n-1
            rows=[f'Write: flash=0x{offset:x} mem=0x{address:x} size={n} ret_size={actual}']
        elif args[0]=='cmp.b':
            a,b,n=map(lambda v:int(v,16),args[1:]);x.require(self.s.ram[a][:n]==self.s.ram[b][:n],'model_byte_mismatch')
            rows=[f'Total of {n} bytes were the same']
            if self.s.scenario=='bad_compare_ack' and self.s.writes==1:rows=[f'Total of {n-1} bytes were the same']
        elif args[0]=='bootm':
            matches=[name for name,data in self.s.images.items() if self.s.ram[c.LOAD].startswith(data)];x.require(len(matches)==1,'model_boot_image');name=matches[0];self.s.boots.append(name)
            if (name=='f361' and self.s.scenario=='f361_bootm_returns') or (name=='f358' and self.s.scenario=='rollback_bootm_returns'):self.s.ready=True;return len(self.s.commands)
            self.s.image=name;self.s.boot_id='new-'+str(len(self.s.boots));return len(self.s.commands)
        else:raise AssertionError(cmd)
        self.s.ready=True;return reply(cmd,*rows)

