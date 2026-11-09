"""File/fake-only checks for ETH73 RAM transfer verification and allowlists."""
import importlib.util,json,pathlib,re,unittest
HERE=pathlib.Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('eth73_exec',HERE/'executor.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e)
class Fake:
 def __init__(self):self.queue=[];self.writes=[];self.now=0;self.size=4000000;self.bad_crc=False;self.bad_entry=False
 def check_safe(self):pass
 def read(self,size=4096,timeout=.1):self.now+=timeout;return self.queue.pop(0) if self.queue else b''
 def write(self,data,timeout=3):
  self.writes.append(data)
  answers={b'printenv filesize\r':f'filesize={self.size:X}\r\ntopaz> '.encode(),
   b'iminfo 83000000\r':('Image Type: ARC Linux Kernel Image (uncompressed)\nData Size: 3991808 Bytes\nLoad Address: 8493a000\nEntry Point: '+('8493e000' if self.bad_entry else '84940000')+'\nVerifying Checksum ... OK\ntopaz> ').encode(),
   b'md.l 84000000 1\r':('84000000: '+('deadbeef' if self.bad_crc else '1234abcd')+'\ntopaz> ').encode(),
   f'crc32 83000000 {self.size:08x} 84000000\r'.encode():b'topaz> '}
  self.queue.append(answers[data]);return len(data)
class Backend:
 def force_lease(self):pass
 def lease(self):pass
class Tests(unittest.TestCase):
 def flow(self):
  stream=Fake();config={'bytes':4000000,'payload_bytes':3991808,'entry':'0x84940000','crc32':'1234abcd'}
  flow=e.Flow(Backend(),stream,'0123abcd',config=config,output=HERE,clock=lambda:stream.now)
  return stream,flow
 def test_uppercase_filesize_new_entry_crc(self):
  s,f=self.flow();f.verify_ram();self.assertEqual(len(s.writes),4)
 def test_bad_crc_stops(self):
  s,f=self.flow();s.bad_crc=True
  with self.assertRaises(e.m.Refusal):f.verify_ram()
  self.assertFalse(any(b'bootm' in b for b in s.writes))
 def test_old_entry_refused(self):
  s,f=self.flow();s.bad_entry=True
  with self.assertRaises(e.m.Refusal):f.verify_ram()
 def test_flash_bootenv_commands_refused(self):
  for command in ['erase all','setenv bootselect 1','saveenv','sf write 0 0 10','reset']:
   s,f=self.flow()
   with self.assertRaises(e.m.Refusal):f.command(command,e.m.PROMPT)
   self.assertEqual(s.writes,[])
 def test_environment_route(self):
  self.assertTrue(e.m.parse_environment(b'bootcmd=bootselect\r\nbootselect=0\r\n'))
  with self.assertRaises(e.m.Refusal):e.m.parse_environment(b'bootcmd=bootselect\nbootselect=1\n')
 def test_powercycle_ready_requires_basic_nonce(self):
  source=(HERE/'executor.py').read_text()
  baseline=source.index('m.qualify_nonce(baseline')
  self.assertLess(baseline,source.index("READY_POWER_CYCLE.json",baseline))
  self.assertIn("prior['reboots']==1",source)
  self.assertIn('self.b.args.baseline_boot',source)
  self.assertNotIn('saveenv',source)
 def test_fast_stop_key_has_no_lease_subprocess(self):
  s,f=self.flow();s.queue=[b'Hit any key to stop autoboot: 2',b'\r\ntopaz> ']
  def write(data,timeout=3):s.writes.append(data);return len(data)
  s.write=write
  class NoLease:
   def lease(self):raise AssertionError('slow lease during capture')
   def force_lease(self):raise AssertionError('slow forced lease during capture')
  f.b=NoLease();f.catch_topaz_fast();self.assertEqual(s.writes,[b' '])
if __name__=='__main__':unittest.main()
