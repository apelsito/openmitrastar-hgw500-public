"""Focused offline cleanup regressions for root's F367 client dispatcher."""
from pathlib import Path
import argparse,json,subprocess,tempfile,unittest
import f367_aelita_dispatcher as gate

class Cleanup(unittest.TestCase):
 def fixture(self,out,mode):
  config=json.loads((gate.ROOT/'configs/f367_aelita_client.json').read_text(encoding='ascii'))
  ready=dict(channel=52,filter_bw=20,cac_done=1,ready=1,tx_admission=1,nop_active=0,cac_active=0,generation=2)
  class Host:
   installed_receipt=dict(image_sha256='a'*64,boot_id='fixture-boot',same_hardware_lease=True)
   def identity(self,name):return dict(boot_id='fixture-boot')
   def snapshot(self):return ready
  class Server:
   def poll(self):return None
   def terminate(self):
    if mode=='terminate':raise OSError('fixture terminate failure')
   def wait(self,timeout):raise subprocess.TimeoutExpired('fixture-server',timeout)
   def kill(self):raise OSError('fixture kill failure')
  class Fake(gate.Dispatcher):
   def __init__(self,*args):super().__init__(*args);self.actions=[];self.removed=False
   def stage_payload(self):pass
   def action(self,name):
    self.actions.append(name)
    if name=='Traffic':raise gate.ClientError('fixture-traffic-failed')
    return dict(status='PASS')
   def snapshot(self):return dict(target_bssid_tag='b'*64,stations=[dict(tag='c'*64,auth=True,assoc=True,authorized=True)])
   def bind_private(self,target):pass
   def remote_json(self,name):return dict(wifi_ipv4='192.168.1.77',client_tag='c'*64)
   def start_server(self,ip):self.firewall_created=True;self.server=Server()
   def firewall(self,ip,create):self.removed=not create
  return Fake(Host(),dict(aelita_config=config,images=dict(f367=dict(sha256='a'*64,version='lyoko-fixture-f367'))),out,ready)

 def check_cleanup(self,mode):
  with tempfile.TemporaryDirectory(prefix='f367-cleanup-') as folder:
   out=Path(folder)/'result';dispatcher=self.fixture(out,mode)
   with self.assertRaises(gate.ClientError):dispatcher.run()
   self.assertEqual(dispatcher.actions[-1],'Restore');self.assertTrue(dispatcher.removed)
   result=json.loads((out/'result.json').read_text(encoding='ascii'));self.assertEqual(result['status'],'FAILED_F367_CLIENT');self.assertTrue(result['firewall_removed']);self.assertIn('server_cleanup_error',result)

 def test_terminate_error_still_removes_firewall_and_persists(self):self.check_cleanup('terminate')
 def test_kill_error_still_removes_firewall_and_persists(self):self.check_cleanup('kill')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);a=p.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cleanup));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
