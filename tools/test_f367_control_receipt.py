"""One targeted receipt check covering failed exit and contained timeout."""
from pathlib import Path
import json,subprocess,tempfile,unittest
from unittest.mock import patch
import f367_campaign_executor as gate

class ReceiptTests(unittest.TestCase):
 def test_failure_and_timeout_are_saved_before_raise_and_redacted(self):
  token='a'*32
  stdout=('OMF367_ERROR reason=fixture token='+token+' mac=01:23:45:67:89:ab\n').encode()
  stderr=b'OMF367_ERROR psk=not-a-real-secret\n'
  for timeout in (False,True):
   class Process:
    returncode=None if timeout else 17
    calls=0
    def communicate(self,**kwargs):
     self.calls+=1
     if timeout and self.calls==1:raise subprocess.TimeoutExpired('fake-ssh',1,output=stdout,stderr=stderr)
     return stdout,stderr
    def kill(self):self.returncode=-9
    def poll(self):return self.returncode
   with tempfile.TemporaryDirectory() as folder:
    host=gate.Host.__new__(gate.Host);host.out=Path(folder);host.children=[]
    host.network_guard=lambda:True;host.ssh_argv=lambda command:['fake-ssh']
    with patch.object(gate.subprocess,'Popen',return_value=Process()):
     with self.assertRaises(gate.Failure):host.raw_control('activate',token)
    paths=list((host.out/'control').glob('*.json'));self.assertEqual(len(paths),1)
    raw=paths[0].read_text();receipt=json.loads(raw)
    self.assertEqual(receipt['action'],'activate');self.assertEqual(receipt['timed_out'],timeout)
    self.assertTrue(receipt['local_transport_contained'])
    self.assertEqual(receipt['streams']['stdout']['bytes'],len(stdout))
    self.assertIn('reason=fixture',raw)
    for private in (token,'01:23:45:67:89:ab','not-a-real-secret'):self.assertNotIn(private,raw)

if __name__=='__main__':unittest.main()
