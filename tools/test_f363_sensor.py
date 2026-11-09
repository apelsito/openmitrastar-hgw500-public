"""Exercise the real thermal orchestration with the proven owner fixture."""
from pathlib import Path
from unittest.mock import patch
import argparse,json,tempfile,unittest
import f363_sensor_executor as x
import f363_sensor_commands as cmd
import test_f356_observe as old
BOOT=old.RAMBOOT
NEW='abcdef01-2345-6789-abcd-ef0123456789'
def owner(token,op=1):
 row=old.owner(token,op);row['boot_id']=BOOT
 if op in (3,6):row['phase']=x.protocol.PHASE
 return row
class Model:
 def __init__(self,scenario):self.scenario=scenario;self.actions=[];self.resets=[];self.active=False
 def reset(self):self.resets.append(1);self.active=False
class Host:
 model=None
 def __init__(self,p,o):self.m=self.model
 def guard(self):return True
 def identity(self,*args):return dict(boot_id=NEW if self.m.resets else BOOT,uts='#358 @1790006400')
 def initial_binding(self,row):return True
 def preflight(self):return dict(control='00000000')
 def verify_configuration(self):return dict(sequence=2,slot='B')
 def verify_store(self):return dict(sha256='same-store')
 def verify_thermal_disabled(self):x.require(not self.m.active,'sensor_still_active');return dict(enabled=False)
 def platform(self,*args):return dict(status='PASS',checks=27)
 def find_node(self):return 'hwmon0'
 def stage(self,run_id):self.m.actions.append('stage')
 def inspect_current(self):return dict(device_opened=0,ready_for_arm=1)
 def launch_owner(self,token):
  self.m.actions.append('launch')
  if self.m.scenario=='launch_lost':raise x.Failure('ssh_deadline')
  return old.PID
 def status(self,token):return owner(token)
 def arm_begin(self,token):
  self.m.actions.append('arm')
  if self.m.scenario=='arm_lost':raise x.Failure('ssh_deadline')
  return owner(token,2),owner(token,3)
 def activate(self,node):
  self.m.actions.append('activate');self.m.active=True
  if self.m.scenario=='activation_failed':return b'activation_rc=1\nenabled=0\nactivation_attempted=1\nactivation_error=-5\n'
  return b'activation_rc=0\nenabled=1\nactivation_attempted=1\nactivation_error=0\n'
 def sample(self,node):
  self.m.actions.append('sample')
  if self.m.scenario=='sample_failed':return b'temp_rc=1\ntemp_mc=\n'
  return b'temp_rc=0\ntemp_mc=65000\ninterval_rc=0\ninterval_mc=60000 65000\n'
 def cease(self,token):self.m.actions.append('cease');return owner(token,6)
 def autonomous_software_reboot(self):self.m.actions.append('software_reboot');self.m.reset()
 def owner_files_gone(self):return bool(self.m.resets)
 def watchdog_inactive(self):return dict(control='00000000')
 def cleanup_unarmed_stage(self):self.m.actions.append('stage_cleanup')
 def contain(self):return True
class Uart:
 def __init__(self,p,g,o):self.m=Host.model;self.reset_times=self.m.resets;self.failed=None;self.fatal=False
 def open(self):self.m.actions.append('uart_observer')
 def checkpoint(self):return 0
 def since(self,start):return b'Boot reached stage 13\n' if self.m.resets else b''
 def close(self):return dict(reader_stopped=True,port_closed=True,reader_error=None)
class Sensor(unittest.TestCase):
 def case(self,scenario):
  m=Model(scenario);Host.model=m
  def reset(uart,count,seconds):
   if not m.resets:m.reset()
   return True
  with tempfile.TemporaryDirectory(prefix='f363-sensor-') as folder,patch.object(x,'wait_reset',reset),patch.object(x.time,'sleep',lambda _:None):
   code=x.run({},Path(folder),Host,Uart);r=json.loads((Path(folder)/'result.json').read_text(encoding='ascii'))
  return m,code,r
 def test_one_activation_three_pairs_and_observer_only_return(self):
  m,code,r=self.case('success');self.assertEqual(code,0);self.assertEqual(m.actions.count('activate'),1);self.assertEqual(m.actions.count('sample'),3);self.assertEqual(m.actions.count('cease'),1);self.assertNotIn('software_reboot',m.actions);self.assertTrue(r['baseline_returned']);self.assertFalse(r['retain_lease_required']);self.assertFalse(r['autoboot_intercept'])
 def test_failed_activation_no_sample_no_retry_and_return(self):
  m,code,r=self.case('activation_failed');self.assertEqual(code,1);self.assertEqual(m.actions.count('activate'),1);self.assertNotIn('sample',m.actions);self.assertTrue(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed'])
 def test_failed_first_sample_stops_sampling(self):
  m,code,r=self.case('sample_failed');self.assertEqual(code,1);self.assertEqual(m.actions.count('sample'),1);self.assertEqual(m.actions.count('activate'),1);self.assertTrue(r['baseline_returned'])
 def test_lost_arm_response_does_not_activate(self):
  m,code,r=self.case('arm_lost');self.assertEqual(code,1);self.assertNotIn('activate',m.actions);self.assertEqual(m.actions.count('arm'),1);self.assertTrue(r['baseline_returned'])
 def test_lost_launch_response_reconciles_idle_owner_then_reboots(self):
  m,code,r=self.case('launch_lost');self.assertEqual(code,1);self.assertIn('owner_reconciled',r);self.assertNotIn('arm',m.actions);self.assertNotIn('activate',m.actions);self.assertEqual(m.actions.count('software_reboot'),1);self.assertTrue(r['baseline_returned'])
 def test_sysfs_commands_are_fixed_and_samples_are_oem_intervals(self):
  stage='/run/openmitrastar/f363-sensor/'+'a'*32;activation=cmd.activation('hwmon0',stage);self.assertEqual(activation.count('/experimental_enable'),1);self.assertNotIn('temp1_input',activation);sample=cmd.sample('hwmon0',stage);self.assertEqual(sample.count('/temp1_input'),1);self.assertEqual(sample.count('/interval '),1)
  with self.assertRaises(x.Failure):cmd.node_path('hwmon0; reboot')
  for raw in [b'temp_rc=0\ntemp_mc=65001\ninterval_rc=0\ninterval_mc=60000 65000\n',b'temp_rc=0\ntemp_mc=65000\ninterval_rc=0\ninterval_mc=60000 70000\n']:
   with self.assertRaises(x.Failure):cmd.sampled(raw)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Sensor));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
