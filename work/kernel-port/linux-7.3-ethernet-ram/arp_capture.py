"""Read-only, ARP-only capture for the owner's PC/HGW Ethernet link.
Retain parsed protocol fields and hashed MACs; never store packet bytes.
"""
from pathlib import Path
import argparse,ctypes as c,hashlib,json,socket,subprocess,threading,time
from datetime import datetime,timezone

class timeval(c.Structure):_fields_=[('sec',c.c_long),('usec',c.c_long)]
class header(c.Structure):_fields_=[('ts',timeval),('caplen',c.c_uint),('wirelen',c.c_uint)]
class bpf(c.Structure):_fields_=[('length',c.c_uint),('insns',c.c_void_p)]

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=12);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 assert 10<=a.seconds<=60
 dll=c.CDLL('C:/Windows/System32/Npcap/wpcap.dll')
 dll.pcap_open_live.argtypes=[c.c_char_p,c.c_int,c.c_int,c.c_int,c.c_char_p];dll.pcap_open_live.restype=c.c_void_p
 dll.pcap_compile.argtypes=[c.c_void_p,c.POINTER(bpf),c.c_char_p,c.c_int,c.c_uint];dll.pcap_compile.restype=c.c_int
 dll.pcap_setfilter.argtypes=[c.c_void_p,c.POINTER(bpf)];dll.pcap_setfilter.restype=c.c_int
 dll.pcap_next_ex.argtypes=[c.c_void_p,c.POINTER(c.POINTER(header)),c.POINTER(c.POINTER(c.c_ubyte))];dll.pcap_next_ex.restype=c.c_int
 dll.pcap_close.argtypes=[c.c_void_p];dll.pcap_freecode.argtypes=[c.POINTER(bpf)]
 dll.pcap_geterr.argtypes=[c.c_void_p];dll.pcap_geterr.restype=c.c_char_p
 err=c.create_string_buffer(256);handle=dll.pcap_open_live(b'\\Device\\NPF_{B75315D5-9F01-448F-A259-C9D8F25D2233}',128,0,100,err)
 if not handle:raise RuntimeError(err.value.decode(errors='replace'))
 compiled=bpf();records=[]
 try:
  rule=b'arp and (host 192.168.1.91 or host 192.168.1.49)'
  if dll.pcap_compile(handle,c.byref(compiled),rule,1,0xffffffff)!=0:raise RuntimeError(dll.pcap_geterr(handle))
  if dll.pcap_setfilter(handle,c.byref(compiled))!=0:raise RuntimeError(dll.pcap_geterr(handle))
  dll.pcap_freecode(c.byref(compiled))
  ping={}
  def run_ping():
   r=subprocess.run(['C:/Windows/System32/ping.exe','-n','4','-w','1500','192.168.1.91'],capture_output=True,timeout=12)
   ping.update(exit_code=r.returncode,responses_ttl64=r.stdout.count(b'TTL=64'))
  worker=threading.Thread(target=run_ping);worker.start();deadline=time.monotonic()+a.seconds
  while time.monotonic()<deadline:
   hp=c.POINTER(header)();dp=c.POINTER(c.c_ubyte)();ret=dll.pcap_next_ex(handle,c.byref(hp),c.byref(dp))
   if ret==0:continue
   if ret<0:raise RuntimeError('pcap_next_ex='+str(ret))
   data=c.string_at(dp,hp.contents.caplen)
   if len(data)<42 or data[12:14]!=b'\x08\x06':continue
   if data[14:20]!=b'\x00\x01\x08\x00\x06\x04':continue
   src=data[22:28];dst=data[32:38]
   records.append({'op':int.from_bytes(data[20:22],'big'),'sender_ip':socket.inet_ntoa(data[28:32]),'target_ip':socket.inet_ntoa(data[38:42]),
    'sender_mac_sha256':hashlib.sha256(src).hexdigest(),'target_mac_sha256':hashlib.sha256(dst).hexdigest(),
    'eth_src_matches_arp_sender':data[6:12]==src,'eth_dst_matches_arp_target':data[0:6]==dst,
    'wire_bytes':hp.contents.wirelen,'captured_utc':datetime.now(timezone.utc).isoformat()})
  worker.join(1)
  report={'schema':'openmitrastar.eth73-arp-only-capture/v1','records':records,'ping':ping,'raw_packets_saved':False,'promiscuous':False,'flash_writes':0,'bootenv_writes':0}
  (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps({'arp_records':len(records),'ops':[(r['op'],r['sender_ip'],r['target_ip']) for r in records],'ping':ping},indent=2))
 finally:dll.pcap_close(handle)

if __name__=='__main__':main()
