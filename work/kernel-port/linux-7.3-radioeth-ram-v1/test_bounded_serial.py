"""Run writer completion/cancellation cases with fake Windows overlapped IO."""
import ctypes,importlib.util,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
import sys
sys.path.insert(0,str(HERE.parents[2]/'work/pydeps'))
from bounded_serial import BoundedSerialWriter,SerialWriteDeadline
class FakeAPI:
 DWORD=ctypes.c_ulong;ERROR_IO_PENDING=997
 def __init__(self,mode):self.mode=mode;self.now=0.;self.cancelled=False;self.waits=[];self.calls=[];self.length=0
 def ResetEvent(self,event):self.calls.append('reset');return 1
 def WriteFile(self,handle,data,size,count,overlapped):
  self.length=size;self.calls.append('write')
  if self.mode=='immediate':count._obj.value=size;return 1
  return 0
 def GetLastError(self):return 997
 def WaitForSingleObject(self,event,ms):
  self.waits.append(ms);self.now+=ms/1000
  if self.mode=='pending' or (self.cancelled and self.mode!='quarantine'):return 0
  return 258
 def GetOverlappedResult(self,handle,ov,count,blocking):
  assert blocking is False;self.calls.append('completion');count._obj.value=self.length if self.mode!='partial' else 3;return 1
 def CancelIoEx(self,handle,ov):self.calls.append('cancel');self.cancelled=True;return 1
class Serial:
 _port_handle=1
 class Overlapped:hEvent=2
 _overlapped_write=Overlapped()
 out_waiting=0
 def reset_output_buffer(self):pass
class Session:
 def __init__(self):self.serial=Serial()
 def check_safe(self):pass
class Tests(unittest.TestCase):
 def test_immediate_and_pending(self):
  for mode in ['immediate','pending']:
   api=FakeAPI(mode);writer=BoundedSerialWriter(Session(),api,lambda:api.now)
   self.assertEqual(writer.write(b'packet',.2),6);self.assertFalse(writer.unsafe)
   self.assertIsNone(writer.pending)
 def test_event_timeout_cancel_completes(self):
  api=FakeAPI('timeout');writer=BoundedSerialWriter(Session(),api,lambda:api.now)
  with self.assertRaises(SerialWriteDeadline):writer.write(b'packet',.1)
  self.assertTrue(api.cancelled);self.assertFalse(writer.unsafe)
  self.assertIn('completion',api.calls);self.assertLessEqual(api.now,1.1)
 def test_uncertain_cancel_quarantines_buffer_and_future_write(self):
  api=FakeAPI('quarantine');writer=BoundedSerialWriter(Session(),api,lambda:api.now)
  with self.assertRaises(SerialWriteDeadline):writer.write(b'packet',.1)
  self.assertTrue(writer.unsafe);self.assertIsNotNone(writer.pending)
  with self.assertRaises(SerialWriteDeadline):writer.write(b'another',.1)
  self.assertEqual(api.calls.count('write'),1)
 def test_partial_packet_is_not_retried(self):
  api=FakeAPI('partial');api.WaitForSingleObject=lambda event,ms:0
  writer=BoundedSerialWriter(Session(),api,lambda:api.now)
  with self.assertRaises(SerialWriteDeadline):writer.write(b'packet',.1)
  self.assertEqual(api.calls.count('write'),1)
if __name__=='__main__':unittest.main()
