"""Only the live #358 adaptation, reusing the already tested F356 model."""
from pathlib import Path
from unittest.mock import patch
import argparse,json,tempfile,unittest
import f359_observe_executor as x
import test_f356_observe as old

class Profile(unittest.TestCase):
 def case(self,scenario):
  model=old.Model(scenario);old.FakeHost.model=model
  class Host(old.FakeHost):
   def identity(self,name):return dict(boot_id=old.BOOT,uts='#358 @1790006400')
   def inspect_current(self):return dict(kernel_profile_verified=1,required_kernel_version='#358 @1790006400')
  prior_owner=old.owner
  def owner(token=old.TOKEN,op=1):row=prior_owner(token,op);row['boot_id']=old.BOOT;return row
  def reset(uart,count,seconds):
   if len(model.reset_times)==count:model.reset()
   return True
  def restore(*a,**kw):model.returns+=1;return dict(identity={'boot_id':'new-f358'},platform={'checks':27},watchdog={'control':'00000000'},readback_error=None)
  with tempfile.TemporaryDirectory(prefix='f359-profile-') as directory,patch.object(old,'owner',owner),patch.object(old,'LOAD',old.LOAD.replace(old.RAMBOOT.encode(),old.BOOT.encode())),patch.object(x,'wait_reset',reset),patch.object(x,'return_f358',restore),patch.object(x.ram,'inactive_hardware',lambda uart:dict(controls=[0,0],counters=[65535,65535])):
   code=x.run({'images':{'f358':{'full_slot_crc32':'4d006632'}},'expected_spi_control':4},Path(directory),Host,old.FakeUart);result=json.loads((Path(directory)/'result.json').read_text(encoding='ascii'))
  return model,code,result
 def test_live_success_has_no_initial_reboot_ram_or_tftp(self):
  m,code,r=self.case('success');self.assertEqual(code,0);self.assertEqual((m.loads,m.observes,m.unloads,m.returns),(1,1,1,1));self.assertEqual(m.ramboots,0);self.assertNotIn('initial_reboot',m.actions);self.assertEqual(r['status'],'PASS_F359_READONLY_OBSERVE_AND_F358_RETURN')
 def test_failed_or_quarantined_observe_never_unloads_and_returns_same_f358(self):
  for scenario in ('unknown_id','quarantined'):
   m,code,r=self.case(scenario);self.assertEqual(code,1);self.assertEqual((m.loads,m.observes,m.unloads,m.returns),(1,1,0,1));self.assertTrue(r['baseline_returned']);self.assertEqual(r['status'],'FAIL_OBSERVE_WITH_F358_RETURN')
 def test_actual_profile_and_owner_launch_are_358(self):
  host=x.Host.__new__(x.Host);host.plan={'images':{'f358':{'version':'lyoko-foundation-6.9.8-f358-config-backend-device','kernel_build':'#358','marker':'F340_WATCHDOG_BASELINE'}}}
  host.ssh=lambda cmd:('boot_id='+old.BOOT+'\nuts=#358 @1790006400\nf340=F340_WATCHDOG_BASELINE\0\nf336=\n').encode();self.assertEqual(host.identity('f358')['uts'],'#358 @1790006400')
  host.stage_dir='/run/openmitrastar/f359/'+'a'*32;host.supervisor=host.stage_dir+'/supervisor';calls=[];host.ssh=lambda cmd:calls.append(cmd) or b'F359_OWNER_PID=1234\n';self.assertEqual(host.launch_owner(old.TOKEN),1234)
  self.assertIn("printf 'F359_OWNER_PID=%s\\n'",calls[0]);self.assertIn("trap '' HUP",calls[0])
 def test_new_uart_scope_has_no_tftp_or_flash_program(self):
  plan=dict(images={'f358':{'bytes':5361664}},protected={'parts':[]},bootargs=x.contract.BOOTARGS)
  words=x.vocabulary(plan);self.assertIn('bootm 0x83000000',words)
  for word in words:self.assertFalse(any(s in word for s in ('tftp','erase','write','saveenv','run ','bootselect')))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Profile));x.save(a.result,dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False,historical_battery_rerun=False));raise SystemExit(0 if r.wasSuccessful() else 1)
