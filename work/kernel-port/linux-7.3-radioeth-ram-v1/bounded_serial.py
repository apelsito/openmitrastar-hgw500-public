"""Windows UART overlapped writes with explicit event deadlines.

Unlike pySerial's Windows backend this never waits in GetOverlappedResult(TRUE).
A cancelled write must complete before the same OVERLAPPED/buffer can be reused.
"""
import ctypes
import threading
import time

class SerialWriteDeadline(TimeoutError):pass

class BoundedSerialWriter:
 def __init__(self,session,api=None,clock=time.monotonic):
  from serial import win32
  self.session=session;self.serial=session.serial;self.api=api or win32
  self.clock=clock;self.lock=threading.Lock();self.unsafe=False;self.pending=None
 def write(self,data,timeout=3):
  if timeout<=0:raise SerialWriteDeadline('UART write has no positive budget')
  self.session.check_safe()
  if self.unsafe:raise SerialWriteDeadline('Previous UART write quarantined')
  if not data:return 0
  if not self.lock.acquire(blocking=False):raise SerialWriteDeadline('Concurrent UART writer')
  try:
   api=self.api;handle=self.serial._port_handle;overlapped=self.serial._overlapped_write
   payload=ctypes.create_string_buffer(bytes(data));self.pending=payload
   count=api.DWORD();deadline=self.clock()+timeout
   if not api.ResetEvent(overlapped.hEvent):raise OSError('UART event reset failed')
   complete=api.WriteFile(handle,payload,len(data),ctypes.byref(count),overlapped)
   error=api.GetLastError() if not complete else 0
   if not complete and error!=api.ERROR_IO_PENDING:raise OSError('UART WriteFile failed')
   if not complete:
    while True:
     self.session.check_safe();remaining=deadline-self.clock()
     if remaining<=0:
      api.CancelIoEx(handle,overlapped)
      status=api.WaitForSingleObject(overlapped.hEvent,1000)
      if status!=0:
       self.unsafe=True;raise SerialWriteDeadline('Cancelled UART write not completed; quarantined')
      api.GetOverlappedResult(handle,overlapped,ctypes.byref(count),False)
      # Cancel completion is proven; caller must never retry partial packet.
      raise SerialWriteDeadline('UART WriteFile deadline expired')
     status=api.WaitForSingleObject(overlapped.hEvent,max(1,min(50,int(remaining*1000))))
     if status==0:break
     if status!=258:
      self.unsafe=True;api.CancelIoEx(handle,overlapped)
      raise OSError('UART event wait failed; quarantined')
    if not api.GetOverlappedResult(handle,overlapped,ctypes.byref(count),False):
     raise OSError('UART completion failed')
   if count.value!=len(data):raise SerialWriteDeadline('UART completed only part of packet')
   # Receiver must see the complete packet before ACK timing begins.
   while self.serial.out_waiting:
    self.session.check_safe()
    if self.clock()>=deadline:
     self.serial.reset_output_buffer()
     raise SerialWriteDeadline('UART TX queue drain deadline expired')
    time.sleep(.002)
   self.pending=None;return count.value
  finally:
   if not self.unsafe:self.pending=None
   self.lock.release()
