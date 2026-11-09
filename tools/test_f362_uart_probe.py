from pathlib import Path
from unittest.mock import Mock
import argparse,json,unittest
import f362_uart_reboot_probe as x
class Tests(unittest.TestCase):
 def capture(self):
  capture=Mock(failed=None,autoboot=False,reset_times=[]);capture.guard.return_value=True;capture.tail.return_value=b'Linux console';capture.serial.is_open=True;capture.serial.out_waiting=0;capture.serial.write.return_value=1;return capture
 def test_exact_break_clear_gap_and_single_b(self):
  cap=self.capture();calls=[];now=[0];record={}
  def sleep(n):calls.append(('sleep',n));now[0]+=n
  x.break_b(cap,record,True,lambda port,on:calls.append(('break',on)),sleep,lambda:now[0]);self.assertEqual(calls,[('break',True),('sleep',.6),('break',False),('sleep',.15)]);cap.serial.write.assert_called_once_with(b'b');self.assertTrue(record['break_cleared'])
 def test_failed_clear_never_sends_b(self):
  cap=self.capture();record={}
  def drive(port,on):
   if not on:raise x.Failure('break_api_failed')
  with self.assertRaises(x.Failure):x.break_b(cap,record,True,drive,lambda _:None)
  cap.serial.write.assert_not_called()
 def test_bootbase_and_disabled_sysrq_refused(self):
  cap=self.capture();cap.tail.return_value=b'topaz> '
  with self.assertRaises(x.Failure):x.break_b(cap,{},True,lambda *a:None,lambda _:None)
  row=dict(boot_id='01234567-89ab-cdef-0123-456789abcdef',uts='#358 @1790006400',kernel='5.10.260-openmitrastar-radiohw',version=x.VERSION,ready='ready',source='journal',sequence='2',active_sha=x.ACTIVE_SHA,lock_absent='1',fatal_count='0',watchdog_control='00000000',sysrq='1');x.valid_snapshot(row);row['sysrq']='0'
  with self.assertRaises(x.Failure):x.valid_snapshot(row)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False))+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
