"""Only target/store, two-port acceptance and serial recovery delta cases."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import argparse,json,tempfile,unittest
import f362_install_contract as c
import f362_install_executor as x
import f362_recovery_delta as d
import f361_install_test_fixture as old
class Delta(unittest.TestCase):
 def test_candidate_and_fallback_include_current_sequence2(self):
  images=c.images();self.assertEqual(images['f362']['full_slot_crc32'],'1a6e28c0');self.assertEqual(images['f361']['full_slot_crc32'],'815b9440');self.assertEqual(c.store_binding()['crc32'],'5d2ee646');c.validate_proofs()
 def serial(self,raw=b'Linux version 5.10.260-openmitrastar-radiohw #358\n',fail_clear=False):
  events=[];uart=SimpleNamespace(failed=None,write_in_flight=False,serial_recovery_record={},kernel_handoff_start=0,autoboot=False,reset_times=[],serial=SimpleNamespace(is_open=True,out_waiting=0))
  uart.since=lambda start:raw if start==0 else b'sysrq: Resetting\nBoot reached stage 13\ntopaz> '
  uart.has_prompt=lambda:False;uart.checkpoint=lambda:len(raw);uart.invalidate_prompt=lambda:events.append('invalidate')
  def stop(seconds):self.assertEqual(seconds,120);events.append('intercept');uart.autoboot=True
  uart.stop_autoboot=stop;uart.serial.write=lambda data:events.append(data) or len(data)
  uart.wait_prompt=lambda timeout,start:uart.reset_times.append(1)
  def drive(port,enabled):
   events.append(enabled)
   if not enabled and fail_clear:raise x.Failure('break_api_failed')
  return uart,events,drive
 def test_serial_interceptor_precedes_single_b_without_ssh(self):
  uart,events,drive=self.serial();host=SimpleNamespace(guard=lambda:True)
  result=d.serial_reboot_to_prompt(host,uart,drive=drive,sleep=lambda s:events.append(s),clock=lambda:0)
  self.assertEqual(events,[True,.6,False,.15,'intercept','invalidate',b'b']);self.assertTrue(result['new_prompt_and_dispatch'])
  with self.assertRaises(x.Failure):d.serial_reboot_to_prompt(host,uart,drive=drive)
 def test_failed_break_clear_never_sends_b(self):
  uart,events,drive=self.serial(fail_clear=True)
  with self.assertRaises(x.Failure):d.serial_reboot_to_prompt(SimpleNamespace(guard=lambda:True),uart,drive=drive,sleep=lambda _:None,clock=lambda:0)
  self.assertNotIn(b'b',events);self.assertFalse(uart.serial_recovery_record['break_cleared'])
 def test_cleanup_only_clears_and_reports_failed_clear(self):
  uart,events,drive=self.serial();uart.serial_recovery_record={'break_attempted':True,'break_cleared':False}
  self.assertTrue(d.clear_pending_break(uart,drive));self.assertEqual(events,[False]);self.assertTrue(uart.serial_recovery_record['cleanup_clear_verified'])
  uart,events,drive=self.serial(fail_clear=True);uart.serial_recovery_record={'break_attempted':True,'break_cleared':False}
  self.assertFalse(d.clear_pending_break(uart,drive));self.assertEqual(events,[False]);self.assertTrue(uart.serial_recovery_record['break_cleanup_failed'])
 def test_bootbase_or_missing_fresh_linux_never_sends_break(self):
  for raw in [b'topaz> ',b'',b'Linux version 5.10.260-openmitrastar-radiohw\nBoot reached stage 13\n']:
   uart,events,drive=self.serial(raw)
   with self.assertRaises(x.Failure):d.serial_reboot_to_prompt(SimpleNamespace(guard=lambda:True),uart,drive=drive)
   self.assertEqual(events,[])
 def test_either_port_carrier_accepted_with_both_in_bridge(self):
  template='eth0_driver=../../../drivers/qtn-topaz-emac-f352\neth0_bridge=1\neth0_carrier=0\neth0_irq=20\neth1_driver=../../../drivers/qtn-topaz-emac-f352\neth1_bridge=1\neth1_carrier=1\neth1_irq=19\nmapping=MAC1/PHY3,MAC0/PHY1\n'
  r=d.verify_ethernet_response(template.encode());self.assertTrue(r['eth1']['carrier']);self.assertFalse(r['eth0']['carrier'])
  for bad in [template.replace('eth1_bridge=1','eth1_bridge=0'),template.replace('eth1_carrier=1','eth1_carrier=0'),template.replace('eth1_irq=19','eth1_irq=20')]:
   with self.assertRaises(x.Failure):d.verify_ethernet_response(bad.encode())
 def test_actual_boot_configuration_requires_sequence2(self):
  host=x.Host({'boot_acceptance':{'payload_sha256':'a'*64}},Path('.'));data=('ready=F361_READY\nslot=B\nsequence=2\nsha256='+'a'*64+'\nsource=journal\nactive_sha256='+'a'*64+'\nallow_hw=Y\nallow_program=Y\n').encode();host.ssh=lambda _:data
  self.assertEqual(host.verify_configuration()['sequence'],2);host.ssh=lambda _:data.replace(b'sequence=2',b'sequence=1')
  with self.assertRaises(x.Failure):host.verify_configuration()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Delta));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
