"""Only new host timeout binding; no network, watchdog, radio or flash."""
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import f367r3_campaign_worker as gate

class BindingTests(unittest.TestCase):
 def test_activate_240_and_other_control_30_keep_receipts(self):
  for action,expected in [('activate',240),('enter-dfs',30)]:
   seen=[]
   class Process:
    returncode=0
    def communicate(self,timeout):seen.append(timeout);return b'OMF367_TEST result=ok\n',b''
    def poll(self):return self.returncode
   with tempfile.TemporaryDirectory() as folder:
    host=gate.Host.__new__(gate.Host);host.out=Path(folder);host.children=[]
    host.network_guard=lambda:True;host.ssh_argv=lambda command:['FAKE_NO_NETWORK']
    with patch.object(gate.subprocess,'Popen',return_value=Process()):
     receipt=host.raw_control(action,'a'*32 if action=='activate' else None)
    self.assertEqual(seen,[expected]);self.assertTrue(Path(receipt['receipt_path']).is_file())

if __name__=='__main__':unittest.main()
