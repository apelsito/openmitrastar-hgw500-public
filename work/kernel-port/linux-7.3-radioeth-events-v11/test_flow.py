"""Exercise the actual new flow with bounded fake receiver and modem."""
from pathlib import Path
import importlib.util,json,sys,tempfile,types,unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('events73',HERE/'executor.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)

class Session:
 def __init__(self,owner):self.owner=owner
 def write(self,data,timeout=3):self.owner.ops.append(data.decode().strip());return len(data)
 def read(self,size=1,timeout=.1):return b''
class Backend:
 def force_lease(self):pass
class FakeFlow(e.Flow):
 def __init__(self,output,fail_nonce=False,bad_map=False):
  self.ops=[];self.fail_nonce=fail_nonce;self.bad_map=bad_map;self.map_reads=0
  super().__init__(Backend(),Session(self),'0123456789abcdef0123456789abcdef',config={'sha256':'fake','image':'fake.bin','bytes':6980384},output=output,clock=lambda:0.)
 def safe(self):pass
 def fresh(self):pass
 def synchronize_nonce(self,kernel):
  self.ops.append('nonce')
  if self.fail_nonce:raise e.m.BASE.Refusal('nonce invalid')
  return kernel+b'\n'
 def catch_topaz_fast(self):self.ops.append('catch')
 def verify_ram(self):self.ops.append('verify-crc')
 def command(self,command,prompt=e.m.PROMPT,seconds=30):
  self.ops.append(command)
  if command.startswith('echo '):return command[5:].encode()+b'\n'
  if command=='printenv bootcmd bootselect':return b'bootcmd=bootselect\nbootselect=0\n'
  if command=='md.l e0000004 1':
   self.map_reads+=1
   return b'e0000004: '+(b'200032af' if self.bad_map and self.map_reads==2 else b'000032af')+b'\n'
  if command=='md.l f4000000 1':return b'f4000000: 00000000\n'
  if command=='memtest':return b'memtest PASS 1MiB two patterns\n'
  if command=='userlandtest':return b'USERLAND_TEST_END SHELL_ARITH_PASS\n'
  if command=='ethload':return b'ETHLOAD=0\n'
  if command=='radioload':return b'RADIO_MODULE_RESULT=0\r\n'*19+b'RADIOLOAD_MODULES_COMPLETE\n'
  return b'eth73> '
 def wait(self,pattern,seconds):return b'Linux version '+e.m.KERNEL+b'\neth73> '

class Recorder:
 def write_result(self,path,outcome):path.write_text(json.dumps({'outcome':outcome}))
class Modem:
 def __init__(self,*args,**kwargs):pass
 def send(self,files,progress):progress(0,'fake',6980384,6980384);return True
class Tests(unittest.TestCase):
 def setUp(self):
  self.original=e.m.preflight;e.m.preflight=lambda config:None
  self.old_modules={x:sys.modules.get(x) for x in ['f323_uart_ymodem_load','uart_ymodem_load']}
  sys.modules['f323_uart_ymodem_load']=types.SimpleNamespace(ControlEventRecorder=Recorder,F323ModemSocket=Modem)
  sys.modules['uart_ymodem_load']=types.SimpleNamespace(ProtocolType=types.SimpleNamespace(YMODEM=1))
 def tearDown(self):
  e.m.preflight=self.original
  for n,v in self.old_modules.items():
   if v is None:sys.modules.pop(n,None)
   else:sys.modules[n]=v
 def test_complete_flow_requires_crc_and_map_before_single_handoff(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=FakeFlow(Path(tmp));r=f.run()
   self.assertEqual(r['status'],'PASS_RADIOETH73_RAM_BOOT_USERLAND_DRIVER_PROBE')
   self.assertEqual(r['reboots'],1);self.assertEqual(r['bootm'],1)
   self.assertLess(f.ops.index('nonce'),f.ops.index('reboot'))
   self.assertLess(f.ops.index('verify-crc'),len(f.ops)-1-f.ops[::-1].index('md.l e0000004 1'))
   self.assertEqual(f.ops.count('bootm 83000000'),1)
 def test_no_reset_on_wrong_nonce(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=FakeFlow(Path(tmp),fail_nonce=True)
   with self.assertRaises(e.m.BASE.Refusal):f.run()
   self.assertNotIn('reboot',f.ops)
 def test_changed_map_blocks_handoff_after_transfer(self):
  with tempfile.TemporaryDirectory() as tmp:
   f=FakeFlow(Path(tmp),bad_map=True)
   with self.assertRaises(e.m.BASE.Refusal):f.run()
   self.assertIn('verify-crc',f.ops);self.assertNotIn('bootm 83000000',f.ops)
if __name__=='__main__':unittest.main()
