"""Actual new flow control, finite fake UART; no hardware or flash."""
from pathlib import Path
import importlib.util,json,re,tempfile,unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('autostart_gate',HERE/'executor.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
class Backend:
 def force_lease(self):pass
class Fake:
 def __init__(self):self.now=0.;self.queue=[];self.sent=[];self.bad_crc=False;self.bad_entry=False;self.compression='lzma compressed'
 def check_safe(self):pass
 def read(self,size=4096,timeout=.1):self.now+=timeout;return self.queue.pop(0) if self.queue else b''
 def write(self,data,timeout=3):
  self.sent.append(data)
  if data==b'printenv filesize\r':reply=b'filesize=5c9141\r\ntopaz> '
  elif data==b'iminfo 83000000\r':
   entry='851b4000' if self.bad_entry else '851b6000'
   reply=('Image Type: ARC Linux Kernel Image ('+self.compression+')\r\nData Size: 6058305 Bytes\r\nLoad Address: 8493a000\r\nEntry Point: '+entry+'\r\nVerifying Checksum ... OK\r\ntopaz> ').encode()
  elif data.startswith(b'crc32 '):reply=b'CRC ready\r\ntopaz> '
  elif data==b'md.l 84000000 1\r':reply=('84000000: '+('00000000' if self.bad_crc else '7018a9aa')+'\r\ntopaz> ').encode()
  else:reply=b'eth73> '
  self.queue.extend([reply[:7],reply[7:]]);return len(data)
class Tests(unittest.TestCase):
 def flow(self):
  uart=Fake();config={'bytes':6066497,'payload_bytes':6058305,'entry':'0x851b6000','crc32':'7018a9aa'}
  return uart,e.Flow(Backend(),uart,'abc123',clock=lambda:uart.now,config=config,output=HERE)
 def test_complete_crc_entry_and_lzma_reply(self):
  uart,flow=self.flow();flow.verify_ram();self.assertEqual(len(uart.sent),4)
 def test_wrong_entry_rejected_without_handoff(self):
  uart,flow=self.flow();uart.bad_entry=True
  with self.assertRaises(e.m.BASE.Refusal):flow.verify_ram()
  self.assertFalse(any(b'bootm' in x for x in uart.sent))
 def test_wrong_crc_rejected_without_handoff(self):
  uart,flow=self.flow();uart.bad_crc=True
  with self.assertRaises(e.m.BASE.Refusal):flow.verify_ram()
  self.assertFalse(any(b'bootm' in x for x in uart.sent))
 def test_uncompressed_response_refused(self):
  uart,flow=self.flow();uart.compression='uncompressed'
  with self.assertRaises(e.m.BASE.Refusal):flow.verify_ram()
 def test_flash_environment_and_manual_radio_actions_refused(self):
  for command in ['spi_flash erase 0x7e0000 0x5e0000','spi_flash write 0x7e0000 0x83000000 0x10','saveenv','setenv bootselect 1','tftpboot 83000000 image','radioap','shell']:
   uart,flow=self.flow()
   with self.assertRaises(e.m.BASE.Refusal):flow.command(command)
   self.assertEqual(uart.sent,[])
 def test_source_requires_auto_marker_and_19modules(self):
  source=(HERE/'executor.py').read_text()
  self.assertIn("b'AUTOSTART_END' in boot",source)
  self.assertIn("count==19",source)
  self.assertNotIn("self.command('radioload'",source)
  self.assertNotIn("self.command('httpsstart'",source)
if __name__=='__main__':unittest.main()
