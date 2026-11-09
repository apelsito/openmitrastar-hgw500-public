"""Execute RAM-only command/CRC/parser controls with a fake UART; no device."""
import importlib.util,json,re,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('radioeth_executor',HERE/'executor.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)

class Fake:
 def __init__(self):self.time=0.;self.queue=[];self.writes=[];self.bad_crc=False;self.bad_entry=False
 def check_safe(self):pass
 def read(self,size=4096,timeout=.1):self.time+=timeout;return self.queue.pop(0) if self.queue else b''
 def write(self,data,timeout=3):
  self.writes.append(data)
  replies={
   b'printenv filesize\r':b'topaz>printenv filesize\r\nfilesize=6A4320\r\ntopaz> ',
   b'iminfo 83000000\r':('topaz>iminfo 83000000\r\nImage Type: ARC Linux Kernel Image (uncompressed)\r\nData Size: 6955808 Bytes\r\nLoad Address: 8493a000\r\nEntry Point: '+('84940000' if self.bad_entry else '84ca4000')+'\r\nVerifying Checksum ... OK\r\ntopaz> ').encode(),
   b'crc32 83000000 006a4320 84000000\r':b'topaz>crc32 83000000 006a4320 84000000\r\nCRC ready\r\ntopaz> ',
   b'md.l 84000000 1\r':('topaz>md.l 84000000 1\r\n84000000: '+('deadbeef' if self.bad_crc else 'df2ab962')+'\r\ntopaz> ').encode(),
  }
  if data in replies:self.queue.extend([replies[data][:7],replies[data][7:]])
  else:self.queue.append(b'eth73> ')
  return len(data)
class Backend:
 def force_lease(self):pass
class Tests(unittest.TestCase):
 def flow(self):
  session=Fake();config={'bytes':6964000,'payload_bytes':6955808,'entry':'0x84ca4000','crc32':'df2ab962'}
  return session,e.Flow(Backend(),session,'0123456789',config=config,output=HERE,clock=lambda:session.time)
 def test_new_big_entry_and_prefixed_echo_are_accepted(self):
  session,flow=self.flow();flow.verify_ram();self.assertEqual(len(session.writes),4)
 def test_bad_crc_never_boots(self):
  session,flow=self.flow();session.bad_crc=True
  with self.assertRaises(e.BASE.Refusal):flow.verify_ram()
  self.assertFalse(any(b'bootm' in x for x in session.writes))
 def test_stale_entry_rejected(self):
  session,flow=self.flow();session.bad_entry=True
  with self.assertRaises(e.BASE.Refusal):flow.verify_ram()
 def test_mutation_and_cleartext_actions_refused(self):
  for command in ['erase all','sf write 83000000 7e0000 10','setenv bootselect 1','saveenv','reset','udpecho','tftp 83000000 kernel','radioap','shell']:
   session,flow=self.flow()
   with self.assertRaises(e.BASE.Refusal):flow.command(command)
   self.assertEqual(session.writes,[])
 def test_new_uart_commands_remain_explicit(self):
  for command in ['eth0txdiag','eth1txdiag','userlandtest','radioload','pcistatus','httpsstart','sshstart']:
   session,flow=self.flow();flow.command(command);self.assertEqual(session.writes,[command.encode()+b'\n'])
 def test_fatal_response_rejected(self):
  session,flow=self.flow();session.queue=[b'Kernel panic - not syncing\n']
  with self.assertRaises(e.BASE.Refusal):flow.wait(e.PROMPT,5)
 def test_fast_autoboot_preserves_receiver_without_lease_spawn(self):
  session,flow=self.flow();session.queue=[b'Hit any key to stop autoboot: 2',b'\r\ntopaz> ']
  session.write=lambda data,timeout=3:session.writes.append(data) or len(data)
  flow.catch_topaz_fast();self.assertEqual(session.writes,[b' '])
if __name__=='__main__':unittest.main()
