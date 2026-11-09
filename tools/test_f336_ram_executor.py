"""Runs the actual F336 controller with fake transport; no device/network I/O."""
from pathlib import Path
from unittest.mock import patch
import argparse,hashlib,io,json,queue,tempfile,time,unittest
import f336_wdt_ram_executor as x

def answer(command,*lines):return (command+'\r\n'+'\r\n'.join(lines)+'\r\ntopaz> ').encode()
class FakeHost:
    scenario='normal';last=None
    def __init__(self,p,o):self.plan=p;self.out=o;self.children=[];self.log=[];self.reboots=0;FakeHost.last=self
    def guard(self):return True
    def identity(self,ram):return dict(boot_id='ram' if ram else 'baseline',marker='F336_WDT_RAM_ONLY' if ram else '',uts='#336 RAM' if ram else '#321 baseline')
    def wait_identity(self,ram,timeout=120):
        if ram and self.scenario in ('wrong_marker','silent_bootm'):raise x.Failure('kernel_identity')
        if not ram and self.scenario=='return_bootm_returned':raise x.Failure('return_timeout')
        v=self.identity(ram);v['boot_id']='ram' if ram else 'returned';return v
    def put_probe(self):self.log.append('put_probe')
    def inspect(self):return dict(event='inspect',ready_for_arm=1,device_opened=0)
    def storage_gate(self):return dict(mtd_writable=False)
    def reboot_to_prompt(self,u,software_recovery=False):
        self.reboots+=1;self.log.append('software_recovery' if software_recovery else 'reboot')
        if self.scenario=='silent_bootm' and self.reboots>1:raise x.Failure('ssh_deadline')
        u.ready=True
    def contain(self):self.log.append('contain');return self.scenario!='contain_failure'
class FakeUart:
    last=None
    def __init__(self,p,g,o):self.plan=p;self.guard=g;self.out=o;self.commands=[];self.ready=False;self.mode='flash';self.crc=0;self.fatal=False;self.failed=None;self.boots=0;FakeUart.last=self
    def open(self):pass
    def has_prompt(self):return self.ready
    def tail(self):return b'\r\ntopaz> ' # Deliberately retain old tail after handoff.
    def command(self,cmd,timeout=15,handoff=False):
        x.require(self.ready,'topaz_prompt_missing');x.require(cmd in x.vocabulary(self.plan),'command_not_allowlisted');self.commands.append(cmd)
        if cmd.startswith('bootm'):
            self.boots+=1;self.ready=FakeHost.scenario=='return_bootm_returned' and self.boots==2;return 0
        if cmd.startswith('setenv'):return answer(cmd)
        if cmd.startswith('printenv'):
            name=cmd.split()[1];value=self.plan['bootargs'] if name=='bootargs' else '192.168.1.90' if name=='ipaddr' else '192.168.1.49'
            return answer(cmd,name+'='+value)
        if cmd.startswith('spi_flash read'):
            if FakeHost.scenario=='read_unconfirmed':return answer(cmd)
            self.mode='flash';return answer(cmd,'Read: flash=0x7e0000 mem=0x83000000 size=7995392 ret_size=7995392')
        if cmd.startswith('tftpboot'):
            if FakeHost.scenario=='tftp_timeout':raise x.Failure('uart_deadline')
            self.mode='kernel';n=self.plan['kernel']['bytes'];return answer(cmd,f'Bytes transferred = {n} (0x{n:x})')
        if cmd.startswith('crc32'):
            self.crc=(0xbd1135df if '0x00517000' in cmd else 0x12345678) if self.mode=='flash' else int(self.plan['kernel']['crc32'],16);return answer(cmd)
        if cmd.startswith('md.l'):
            addr=int(cmd.split()[1],16);return answer(cmd,f'{addr:08x}: {self.crc if addr==0x84000000 else 0:08x}')
        if cmd.startswith('iminfo'):return answer(cmd,'## Checking Image at 83000000 ...','Load Address: 8493a000','Entry Point: 8493e000','   Verifying Checksum ... OK')
        raise AssertionError(cmd)
    def close(self):return dict(reader_stopped=True,port_closed=True,reader_error=None)
class FakeServer:
    last=None
    def __init__(self,**kw):self.closed=False;FakeServer.last=self
    def start(self,*a,**kw):return {}
    def finish(self):return dict(status='PASS_TFTP_SINGLE_TRANSFER')
    def close(self):self.closed=True;return FakeHost.scenario!='server_contain_failure'

class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.out=Path(self.tmp.name);p=self.out/'kernel.bin';p.write_bytes(b'KERNEL')
        self.plan=dict(kernel=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size,crc32='12345678'),bootargs='root=31:3 ro')
        FakeHost.scenario='normal'
    def tearDown(self):self.tmp.cleanup()
    def run_flow(self,scenario='normal',mode='inspect',experiment=None):
        FakeHost.scenario=scenario
        with patch.object(x,'Host',FakeHost),patch.object(x,'Capture',FakeUart),patch.object(x,'ScopedTftpProcess',FakeServer),patch.object(x.time,'sleep',lambda _:None),patch.object(x.sys,'stdin',io.StringIO('ARM\n')),patch.object(x,'experiment',experiment or (lambda *_:self.fail('unexpected ARM'))):
            rc=x.run(self.plan,self.out,mode)
        return rc,json.loads((self.out/'result.json').read_text())
    def test_inspect_never_arms_and_returns_once(self):
        rc,r=self.run_flow();self.assertEqual(rc,0);self.assertEqual(r['status'],'PASS_RAM_INSPECT_AND_F321_RETURN');self.assertEqual(FakeUart.last.boots,2);self.assertTrue(r['containment_confirmed'])
    def test_wrong_marker_fails_then_software_returns(self):
        rc,r=self.run_flow('wrong_marker');self.assertEqual(rc,1);self.assertEqual(r['software_recovery'],'F321_RETURNED_NOT_WDT_PASS');self.assertNotIn('put_probe',FakeHost.last.log)
    def test_returning_f321_bootm_never_retried(self):
        rc,r=self.run_flow('return_bootm_returned');self.assertEqual(rc,1);self.assertEqual(FakeUart.last.boots,2);self.assertNotIn('software_recovery',r)
    def test_silent_ram_bootm_does_not_reuse_old_prompt(self):
        rc,r=self.run_flow('silent_bootm');self.assertEqual(rc,1);commands=FakeUart.last.commands;first=commands.index('bootm 0x83000000');self.assertEqual(commands[first+1:],[])
    def test_tftp_timeout_contained_before_return(self):
        rc,r=self.run_flow('tftp_timeout');self.assertEqual(rc,1);self.assertTrue(FakeServer.last.closed);self.assertEqual(FakeUart.last.boots,1);self.assertEqual(r['software_recovery'],'F321_RETURNED_NOT_WDT_PASS')
    def test_unconfirmed_spi_read_never_crc(self):
        rc,r=self.run_flow('read_unconfirmed');self.assertEqual(rc,1);self.assertFalse(any(c.startswith('crc32') for c in FakeUart.last.commands))
    def test_ssh_containment_failure_cannot_pass(self):
        rc,r=self.run_flow('contain_failure');self.assertEqual(rc,1);self.assertEqual(r['status'],'FAILED_CONTAINMENT');self.assertFalse(r['containment_confirmed'])
    def test_server_containment_failure_cannot_pass(self):
        rc,r=self.run_flow('server_contain_failure');self.assertEqual(rc,1);self.assertFalse(r['containment_confirmed'])
    def test_foreign_pet_is_negative_despite_recovery(self):
        def bad(h,u,e):e.append(dict(event='controller_negative_verdict',result='foreign_pet'));raise x.Failure('foreign_pet_observed')
        rc,r=self.run_flow(mode='experiment',experiment=bad);self.assertEqual(rc,1);self.assertEqual(r['software_recovery'],'F321_RETURNED_NOT_WDT_PASS');self.assertTrue(r['trace']['fallback_reset_requested'])
    def test_no_reset_is_negative_despite_recovery(self):
        def bad(h,u,e):raise x.Failure('watchdog_no_reset')
        rc,r=self.run_flow(mode='experiment',experiment=bad);self.assertEqual(rc,1);self.assertEqual(r['error'],'watchdog_no_reset')
    def test_literal_vocabulary_excludes_mutations(self):
        allowed=x.vocabulary(self.plan)
        for value in ('saveenv','run bootcmd','bootselect','runningbootcmd','spi_flash write 0 0 1','spi_flash erase 0 1','sf probe','bootm 0x83000004'):
            self.assertNotIn(value,allowed)
        self.assertFalse(any(';' in c or '\n' in c for c in allowed))
    def test_read_parser_rejects_error_even_with_receipt(self):
        class Bad:
            def command(self,cmd,timeout=15):return answer(cmd,"Read: 'read' : failed : ret=-1",'Read: flash=0x7e0000 mem=0x83000000 size=7995392 ret_size=7995392')
        with self.assertRaises(Exception):x.flash_snapshot(Bad())
    def test_redaction_does_not_publish_unknown_lines(self):
        self.assertEqual(x.redact(b'arbitrary client-secret-value'),'[unclassified-line-redacted]')
        self.assertEqual(x.redact(b'PSK=secret'),'[sensitive-line-redacted]')
        self.assertNotIn('aa:bb',x.redact(b'Linux version aa:bb:cc:dd:ee:ff'))

class FakeSerial:
    def __init__(self):self.is_open=False;self.q=queue.Queue();self.writes=[];self.in_waiting=0
    def open(self):self.is_open=True
    def close(self):self.is_open=False
    def read(self,n):
        try:return self.q.get(timeout=.01)
        except queue.Empty:return b''
    def write(self,data):self.writes.append(data);return len(data)
class CaptureTests(unittest.TestCase):
    def test_actual_capture_handoff_invalidates_stale_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            serial=FakeSerial();p=dict(kernel=dict(path='kernel.bin',bytes=6),bootargs='root=31:3 ro');c=x.Capture(p,lambda:True,Path(d),serial_factory=lambda:serial);c.open()
            try:
                serial.q.put(b'\r\ntopaz> ');c.wait_prompt(1);c.command('bootm 0x83000000',handoff=True);self.assertFalse(c.has_prompt())
                with self.assertRaises(x.Failure):c.command('spi_flash read 0x007e0000 0x83000000 0x007a0000')
                self.assertEqual(serial.writes,[b'bootm 0x83000000\r'])
            finally:c.close()

class RebootTransportTests(unittest.TestCase):
    def check_reboot_timeout(self,fresh_prompt,containment=True):
        with tempfile.TemporaryDirectory() as d:
            serial=FakeSerial();plan=dict(kernel=dict(path='kernel.bin',bytes=6),bootargs='root=31:3 ro');u=x.Capture(plan,lambda:True,Path(d),serial_factory=lambda:serial);u.open()
            host=x.Host(plan,Path(d));host.guard=lambda:True;host.ssh_argv=lambda command:['ssh-fixture',command]
            serial.q.put(b'\r\ntopaz> ');u.wait_prompt(1);wait=u.wait_prompt
            u.wait_prompt=lambda timeout,start=None:wait(.08,start)
            class TimedOut:
                def __init__(self,*a,**kw):self.calls=0;self.returncode=None;self.killed=False
                def communicate(self,*a,**kw):
                    self.calls+=1
                    if self.calls==1:
                        if fresh_prompt:serial.q.put(b'\0Boot reached stage 13\r\ntopaz> ');time.sleep(.02)
                        raise x.subprocess.TimeoutExpired('ssh-fixture',12)
                    if not containment:raise x.subprocess.TimeoutExpired('ssh-fixture',3)
                    return b'',b''
                def kill(self):self.killed=True;self.returncode=-9 if containment else None
                def poll(self):return self.returncode
            try:
                with patch.object(x.subprocess,'Popen',TimedOut):
                    if fresh_prompt and containment:host.reboot_to_prompt(u)
                    else:
                        with self.assertRaisesRegex(x.Failure,'topaz_prompt_timeout' if containment else 'ssh_containment_unproven'):host.reboot_to_prompt(u)
                self.assertTrue(host.children[0].killed)
                self.assertEqual(bool(host.transport_events),containment)
                if containment:self.assertFalse(host.transport_events[0]['reboot_proven'])
            finally:u.close()
    def test_real_host_reboot_timeout_accepts_only_new_uart_prompt(self):self.check_reboot_timeout(True)
    def test_real_host_reboot_timeout_rejects_silence_and_old_prompt(self):self.check_reboot_timeout(False)
    def test_real_host_reboot_rejects_uncontained_ssh(self):self.check_reboot_timeout(True,False)
    def test_expected_disconnect_scope_is_only_reboot(self):
        h=x.Host({},Path('.'))
        with patch.object(x.subprocess,'Popen') as launch:
            with self.assertRaisesRegex(x.Failure,'disconnect_scope'):h.ssh('cat /proc/version',allow_disconnect=True)
            launch.assert_not_called()
    def test_autoboot_old_tail_not_replayed(self):
        with tempfile.TemporaryDirectory() as d:
            serial=FakeSerial();p=dict(kernel=dict(path='kernel.bin',bytes=6),bootargs='root=31:3 ro');c=x.Capture(p,lambda:True,Path(d),serial_factory=lambda:serial);c.open();c.stop_autoboot(1)
            try:
                serial.q.put(b'Hit any key to stop autoboot: 1\r\n');time.sleep(.05)
                for _ in range(5):serial.q.put(b'.');time.sleep(.02)
                self.assertEqual(serial.writes,[b' \r'])
            finally:c.close()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);args=ap.parse_args()
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(t) for t in (Flow,CaptureTests,RebootTransportTests)])
    r=unittest.TextTestRunner(verbosity=2).run(suite);args.result.write_text(json.dumps(dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),passed=r.wasSuccessful(),hardware_actions=False),indent=2)+'\n');raise SystemExit(0 if r.wasSuccessful() else 1)
