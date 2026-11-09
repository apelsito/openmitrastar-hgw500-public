"""Run the actual F346 pipeline against an in-memory flash/UART/host model."""
from pathlib import Path
from unittest.mock import patch
import argparse,copy,hashlib,json,tempfile,unittest
import f346_install_executor as x
import f346_install_contract as c

def reply(command,*rows):return (command+'\r\n'+'\r\n'.join(rows)+'\r\ntopaz> ').encode()
class Model:
    def __init__(self,plan,scenario):
        self.plan=plan;self.scenario=scenario;self.images={n:Path(v['path']).read_bytes() for n,v in plan['images'].items()}
        self.flash=bytearray(self.images['f321']+b'\xff'*(c.SLOT-len(self.images['f321'])))
        self.parts={(v['offset'],v['bytes']):Path(v['path']).read_bytes() for v in plan['protected']['parts']}
        self.ram={};self.commands=[];self.events=[];self.writes=0;self.erases=0;self.boots=[];self.image='f321';self.boot_id='initial';self.ready=False;self.crc=0;self.fail_used=False
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
        return dict(path='synthetic-backup-receipt-no-file',sha256=self.plan['images']['f321']['sha256'],fresh_physical_dump=False,private_acl_applied=True)
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
        if name=='f340' and self.s.scenario in ('platform_fails','rollback_bootm_returns','rollback_write_fails','containment_fails'):raise x.Failure('platform_gate')
        return dict(status='PASS',checks=27)
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
            if (name=='f340' and self.s.scenario=='f340_bootm_returns') or (name=='f321' and self.s.scenario=='rollback_bootm_returns'):self.s.ready=True;return len(self.s.commands)
            self.s.image=name;self.s.boot_id='new-'+str(len(self.s.boots));return len(self.s.commands)
        else:raise AssertionError(cmd)
        self.s.ready=True;return reply(cmd,*rows)

class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=dict(images=c.images(),protected=c.protected_backups(),bootargs=c.BOOTARGS,erased_prefix_crc32=c.crc(b'\xff'*c.PREFIX),erased_store_crc32=c.crc(b'\xff'*c.STORE_BYTES))
    def case(self,scenario):
        s=Model(self.plan,scenario);FakeHost.model=s
        with tempfile.TemporaryDirectory(prefix='f346-offline-') as d:
            with patch.object(x.base.time,'sleep',lambda seconds:None):code=x.run(self.plan,Path(d),FakeHost,FakeUart,FakeServer)
            result=json.loads((Path(d)/'result.json').read_text(encoding='ascii'))
        self.assertEqual(s.flash[c.PREFIX:],b'\xff'*c.STORE_BYTES if scenario!='store_not_erased' else b'\xff'*7+b'\0'+b'\xff'*(c.STORE_BYTES-8))
        self.assertFalse(any(cmd in ('bootselect','run bootcmd','saveenv') or 'unlock' in cmd or 'test' in cmd for cmd in s.commands))
        return s,code,result
    def test_install_and_keep_f340_without_arming(self):
        s,code,r=self.case('success');self.assertEqual(code,0);self.assertEqual(s.image,'f340');self.assertEqual(s.erases,1);self.assertEqual(s.writes,1);self.assertEqual(s.boots,['f340']);self.assertTrue(r['containment_confirmed']);self.assertFalse(r['watchdog_arm_requested'])
    def test_no_lease_or_changed_nonce_has_no_hardware_effect(self):
        for scenario in ('no_lease','nonce_boot_changed'):
            s,code,r=self.case(scenario);self.assertEqual(code,1);self.assertNotIn('serial-open',s.events);self.assertEqual(s.erases,0)
    def test_early_protected_store_selector_failure_returns_readonly_f321(self):
        for scenario in ('protected_changed','store_not_erased','selector_changed'):
            s,code,r=self.case(scenario);self.assertEqual(code,1);self.assertEqual(s.erases,0);self.assertEqual(s.writes,0)
            self.assertEqual(s.boots,['f321']);self.assertEqual(r['status'],'FAILED_F340_WITH_EXACT_F321_RETURN')
    def test_watchdog_active_blocks_even_readonly_boot(self):
        s,code,r=self.case('wdt_persists_in_bootbase');self.assertEqual(code,1);self.assertEqual(s.erases,0);self.assertEqual(s.writes,0);self.assertFalse(s.boots)
    def test_network_drift_after_erase_cannot_interrupt_cached_program(self):
        s,code,r=self.case('network_drifts_after_erase');self.assertEqual(code,1);self.assertEqual(s.erases,1);self.assertEqual(s.writes,1)
        self.assertLess(s.events.index('write'),s.events.index('network-rejected'));self.assertTrue(bytes(s.flash).startswith(s.images['f340']))
    def test_bad_transfer_returns_f321_without_flash_write(self):
        s,code,r=self.case('bad_ram_transfer');self.assertEqual(code,1);self.assertEqual(s.erases,0);self.assertEqual(s.boots,['f321']);self.assertEqual(r['status'],'FAILED_F340_WITH_EXACT_F321_RETURN')
    def test_failed_platform_or_inactive_check_restores_once(self):
        for scenario in ('platform_fails','wdt_unexpectedly_armed'):
            s,code,r=self.case(scenario);self.assertEqual(code,1);self.assertEqual(s.image,'f321');self.assertEqual(s.erases,2);self.assertEqual(s.writes,2);self.assertEqual(s.boots,['f340','f321']);self.assertEqual(r['return_platform']['checks'],27)
    def test_known_erase_write_or_compare_failure_restores_once(self):
        for scenario in ('incomplete_erase','bad_write_ack','bad_compare_ack'):
            s,code,r=self.case(scenario);self.assertEqual(code,1);self.assertEqual(s.image,'f321');self.assertEqual(s.erases,2);self.assertEqual(s.boots,['f321']);self.assertTrue(r['rollback_attempted'])
    def test_unknown_write_completion_never_restarts_or_restores(self):
        s,code,r=self.case('write_timeout');self.assertEqual(code,1);self.assertEqual(s.erases,1);self.assertEqual(s.writes,1);self.assertFalse(s.boots);self.assertTrue(r['flash_command_in_flight']);self.assertTrue(r['retain_lease_required'])
    def test_returned_f340_bootm_not_retried(self):
        s,code,r=self.case('f340_bootm_returns');self.assertEqual(code,1);self.assertEqual(s.boots,['f340','f321']);self.assertEqual(s.image,'f321')
    def test_failed_f321_restore_or_boot_is_terminal(self):
        for scenario in ('rollback_bootm_returns','rollback_write_fails'):
            s,code,r=self.case(scenario);self.assertEqual(code,1);self.assertEqual(s.erases,2);self.assertEqual(s.writes,2);self.assertEqual(s.boots.count('f340'),1);self.assertLessEqual(s.boots.count('f321'),1);self.assertEqual(r['status'],'FAILED_RECOVERY_UNPROVEN_NO_RETRY')
    def test_uncontained_helpers_prevent_new_writer(self):
        for scenario in ('server_uncontained','containment_fails'):
            s,code,r=self.case(scenario);self.assertEqual(code,1);self.assertTrue(r['retain_lease_required']);self.assertFalse(r['containment_confirmed']);self.assertLessEqual(s.erases,1)
    def test_write_vocabulary_is_not_enabled_before_preflight(self):
        allowed=x.vocabulary(self.plan);self.assertNotIn(x.ERASE_COMMAND,allowed)
        for image in self.plan['images'].values():self.assertNotIn(x.write_command(image),allowed)
        self.assertTrue(all(';' not in cmd and '\n' not in cmd for cmd in allowed));self.assertFalse(any('unlock_hw' in cmd for cmd in allowed))
    def test_read_receipt_not_crc_of_stale_memory_is_required(self):
        class Silent:
            def command(self,cmd,timeout=15):return reply(cmd)
        with self.assertRaisesRegex(x.Failure,'flash_read_not_confirmed'):x.flash_read(Silent(),c.LIVE,c.SLOT)
    def test_mutation_method_cannot_bypass_enable_or_order(self):
        FakeHost.model=Model(self.plan,'success');u=FakeUart(self.plan,lambda:True,Path('.'));u.s.ready=True
        with self.assertRaisesRegex(x.Failure,'write_cycle_not_enabled'):u.mutate(x.ERASE_COMMAND)
        u.enable_writer(self.plan['images']['f340'])
        with self.assertRaisesRegex(x.Failure,'write_order_or_repeat'):u.mutate(x.write_command(self.plan['images']['f340']))
        self.assertFalse(u.s.commands)

class HostTests(unittest.TestCase):
    def host(self,output):
        host=x.Host({'images':copy.deepcopy(c.SPECS)},Path('.'));calls=[]
        def ssh(command):calls.append(command);return output
        host.ssh=ssh;return host,calls
    def test_f340_marker_nul_and_runtime_minimal_commands(self):
        host,calls=self.host(b'boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#340 @1790006400\nf340=F340_WATCHDOG_BASELINE\0\nf336=\n')
        row=host.identity('f340');self.assertEqual(row['f340'],'F340_WATCHDOG_BASELINE');self.assertEqual(len(calls),1)
        self.assertIn('then cat /proc/device-tree/openmitrastar,f340-watchdog-baseline;',calls[0])
        for term in ['tr -d','command -v','timeout ','rmdir ','f334']:self.assertNotIn(term,calls[0])
    def test_f336_ram_cannot_impersonate_f321_or_f340(self):
        for expected in ('f321','f340'):
            host,_=self.host(b'boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#336 @1790006400\nf340=\nf336=F336_WDT_RAM_ONLY\0\n')
            with self.assertRaisesRegex(x.Failure,'kernel_identity'):host.identity(expected)
    def test_build_number_match_is_exact(self):
        host,_=self.host(b'boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#3400 @1790006400\nf340=F340_WATCHDOG_BASELINE\0\nf336=\n')
        with self.assertRaisesRegex(x.Failure,'kernel_identity'):host.identity('f340')
    def test_inactive_framework_cannot_hide_hardware_enable(self):
        for change in ({'control':'00000001'},{'device_opened':1}):
            state=dict(event='inspect',ready_for_arm=1,device_opened=0,control_valid=1,control='00000000',framework_inactive=1);state.update(change)
            host,_=self.host(json.dumps(state).encode())
            with self.assertRaisesRegex(x.Failure,'watchdog_not_inactive'):host.watchdog_inactive()
    def test_initial_boot_is_bound_to_original_nonce(self):
        host=x.Host({},Path('.'))
        with patch.dict(x.os.environ,{'OM_F346_CONTEXT':json.dumps({'initial_boot_id':'one'})}):
            self.assertTrue(host.initial_binding({'boot_id':'one'}));self.assertFalse(host.initial_binding({'boot_id':'two'}))
    def test_wait_identity_ignores_old_full_tail_prompt(self):
        host=x.Host({},Path('.'));seen=[]
        class Uart:
            failed=None
            def has_prompt(self):return True
            def since(self,start):seen.append(start);return b''
        calls=[]
        def identify(name):
            calls.append(name)
            if len(calls)==1:raise x.Failure('ssh_failed')
            return {'boot_id':'new'}
        host.identity=identify
        with patch.object(x.time,'sleep',lambda seconds:None):self.assertEqual(host.wait_identity('f340',Uart(),123)['boot_id'],'new')
        self.assertEqual(seen,[123,123])
    def test_wait_identity_rejects_only_new_handoff_prompt(self):
        host=x.Host({},Path('.'))
        class Uart:
            failed=None
            def since(self,start):return b'bootm 0x83000000\r\nfailed\r\ntopaz> '
        with self.assertRaisesRegex(x.Failure,'bootm_returned_no_retry'):host.wait_identity('f340',Uart(),123)
    def test_backup_applies_private_acl_before_copy(self):
        with tempfile.TemporaryDirectory(prefix='f346-acl-fixture-') as d:
            root=Path(d);source=root/'synthetic.bin';source.write_bytes(b'SYNTHETIC NO SECRETS');events=[]
            host=x.Host({'images':{'f321':{'path':str(source),'sha256':c.sha(source)}}},root/'test-run')
            def acl(path,directory):
                events.append((path,directory))
                if directory:self.assertFalse((path/'backup-reference-f321.webformat.bin').exists())
            with patch.object(c,'DEVICE',root/'device/firmware'),patch.object(x,'restrict_acl',acl):record=host.backup_reference()
            self.assertEqual([v[1] for v in events],[True,False]);self.assertTrue(record['private_acl_applied']);self.assertEqual(Path(record['path']).read_bytes(),source.read_bytes())

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(t) for t in (Flow,HostTests));r=unittest.TextTestRunner(verbosity=2).run(suite)
    a.result.write_text(json.dumps(dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),passed=r.wasSuccessful(),hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
