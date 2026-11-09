"""F367 dispatcher cleanup tests with fake network/PowerShell/server actions."""
from pathlib import Path
import json,tempfile,unittest
import f367_aelita_dispatcher as gate

class DispatcherTests(unittest.TestCase):
 def fixture(self,out,mode):
  config=json.loads((gate.ROOT/'configs/f367_aelita_client.json').read_text());image=dict(sha256='a'*64,version='lyoko-test-f367')
  ready=dict(channel=52,filter_bw=20,cac_done=1,ready=1,tx_admission=1,nop_active=0,cac_active=0,generation=2)
  class Host:
   installed_receipt=dict(image_sha256='a'*64,version='lyoko-test-f367',boot_id='test-boot',same_hardware_lease=True)
   def identity(self,name):return dict(boot_id='test-boot')
   def snapshot(self):return ready
  class Fake(gate.Dispatcher):
   def __init__(self,*a):super().__init__(*a);self.actions=[];self.firewalls=[]
   def stage_payload(self):pass
   def action(self,name):
    self.actions.append(name)
    if mode=='capture-failure' and name=='Capture':raise gate.ClientError('capture-failure')
    return dict(status='PASS')
   def snapshot(self):return dict(target_bssid_tag='b'*64,stations=[dict(tag='c'*64,auth=True,assoc=True,authorized=True)])
   def bind_private(self,target):pass
   def remote_json(self,name):return dict(wifi_ipv4='192.168.1.77',client_tag='c'*64)
   def firewall(self,ip,create):
    self.firewalls.append(create)
    if create:raise gate.ClientError('uncertain-firewall-create')
  return Fake(Host(),dict(aelita_config=config,images=dict(f367=image)),out,ready)
 def test_capture_failure_still_attempts_restore(self):
  with tempfile.TemporaryDirectory() as folder:
   dispatcher=self.fixture(Path(folder)/'result','capture-failure')
   with self.assertRaises(gate.ClientError):dispatcher.run()
   self.assertEqual(dispatcher.actions,['Capture','Restore'])
 def test_uncertain_firewall_creation_attempts_exact_cleanup(self):
  with tempfile.TemporaryDirectory() as folder:
   dispatcher=self.fixture(Path(folder)/'result','firewall-failure')
   with self.assertRaises(gate.ClientError):dispatcher.run()
   self.assertEqual(dispatcher.firewalls,[True,False]);self.assertEqual(dispatcher.actions[-1],'Restore')
if __name__=='__main__':unittest.main()
