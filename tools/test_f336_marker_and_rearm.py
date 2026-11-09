"""Offline regressions from F336 attempt 2; no live UART or SSH."""
from pathlib import Path
from unittest.mock import patch
import argparse,json,queue,tempfile,time,unittest
import f336_wdt_ram_executor as x

class MarkerTests(unittest.TestCase):
    def identity(self,stdout,stderr=b''):
        calls=[]
        class Process:
            returncode=0
            def __init__(self,argv,**kw):calls.append(argv[-1])
            def communicate(self,*a,**kw):return stdout,stderr
        host=x.Host({},Path('.'));host.ssh_argv=lambda command:['fake-ssh',command]
        with patch.object(x.subprocess,'Popen',Process):result=host.identity(True)
        return result,calls
    def test_actual_host_identity_reads_nul_marker_without_tr(self):
        result,calls=self.identity(b'boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#336 @1790006400\nmarker=F336_WDT_RAM_ONLY\0\n')
        self.assertEqual(result['marker'],'F336_WDT_RAM_ONLY');self.assertEqual(len(calls),1)
        self.assertIn('then cat /proc/device-tree/openmitrastar,f336-wdt-ram;',calls[0])
        for forbidden in ['tr -d','command -v','timeout ','rmdir ']:self.assertNotIn(forbidden,calls[0])
    def test_stderr_cannot_be_normalized_to_success(self):
        with self.assertRaisesRegex(x.Failure,'ssh_failed'):
            self.identity(b'boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#336\nmarker=F336_WDT_RAM_ONLY\0\n',b'ash: tr: not found\n')
    def test_embedded_nul_is_not_a_valid_marker(self):
        with self.assertRaisesRegex(x.Failure,'marker_encoding'):
            self.identity(b'boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#336\nmarker=F336_WDT\0_RAM_ONLY\0\n')
    def test_wrong_marker_cannot_be_ram(self):
        with self.assertRaisesRegex(x.Failure,'kernel_identity'):
            self.identity(b'boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#336\nmarker=F321\0\n')

class Serial:
    def __init__(self):self.is_open=False;self.q=queue.Queue();self.writes=[];self.in_waiting=0
    def open(self):self.is_open=True
    def close(self):self.is_open=False
    def read(self,n):
        try:
            item=self.q.get(timeout=.01)
            if isinstance(item,Exception):raise item
            return item
        except queue.Empty:return b''
    def write(self,value):self.writes.append(value);return len(value)
def wait_for(condition):
    until=time.monotonic()+1
    while time.monotonic()<until:
        if condition():return
        time.sleep(.005)
    raise AssertionError('fixture deadline')
class RearmTests(unittest.TestCase):
    def test_rearm_ignores_four_old_events_and_accepts_new_zhal(self):
        with tempfile.TemporaryDirectory() as d:
            serial=Serial();u=x.Capture(dict(kernel=dict(path='kernel.bin',bytes=1),bootargs='ro'),lambda:True,Path(d),serial_factory=lambda:serial)
            u.open();u.stop_autoboot(30)
            try:
                for i in range(4):serial.q.put(f'Hit any key event {i}\n'.encode());wait_for(lambda:len(serial.writes)==i+1)
                self.assertEqual(u.auto_count,4);old=u.checkpoint();u.stop_autoboot(30);self.assertEqual(u.auto_floor,old)
                serial.q.put(b'ZHAL> ');wait_for(lambda:len(serial.writes)==5)
                self.assertEqual(serial.writes[-1],b'\x15\x08ATGU\r');self.assertEqual(u.auto_count,1);self.assertIsNone(u.failed)
            finally:u.close()
    def test_reader_preserves_fixed_failure_code(self):
        with tempfile.TemporaryDirectory() as d:
            serial=Serial();u=x.Capture(dict(kernel=dict(path='kernel.bin',bytes=1),bootargs='ro'),lambda:True,Path(d),serial_factory=lambda:serial);u.open()
            serial.q.put(x.Failure('autoboot_events_exceeded'));wait_for(lambda:u.failed is not None)
            result=u.close();self.assertEqual(result['reader_error'],'autoboot_events_exceeded');self.assertEqual(result['reader_error_type'],'Failure')
    def test_reader_does_not_log_driver_exception_text(self):
        with tempfile.TemporaryDirectory() as d:
            serial=Serial();u=x.Capture(dict(kernel=dict(path='kernel.bin',bytes=1),bootargs='ro'),lambda:True,Path(d),serial_factory=lambda:serial);u.open()
            serial.q.put(RuntimeError('sensitive raw UART contents'));wait_for(lambda:u.failed is not None)
            result=u.close();self.assertEqual(result['reader_error'],'uart_reader_failed');self.assertEqual(result['reader_error_type'],'RuntimeError');self.assertNotIn('sensitive',json.dumps(result))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);args=ap.parse_args()
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(t) for t in (MarkerTests,RearmTests));r=unittest.TextTestRunner(verbosity=2).run(suite)
    args.result.write_text(json.dumps(dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),passed=r.wasSuccessful(),hardware_actions=False),indent=2)+'\n');raise SystemExit(0 if r.wasSuccessful() else 1)
