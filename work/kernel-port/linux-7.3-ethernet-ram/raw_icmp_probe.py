"""Finite unicast ICMP probe to the owner HGW eth1, bypassing host ARP lookup.
Uses existing Npcap; retains hashes/counts, never packet contents or MAC values.
"""
from pathlib import Path
import argparse,ctypes as c,hashlib,importlib.util,json,secrets,socket,struct,subprocess,time
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pcap_types',HERE/'arp_capture.py');types=importlib.util.module_from_spec(spec);spec.loader.exec_module(types)
def checksum(data):
 if len(data)&1:data+=b'\0'
 value=sum(struct.unpack('>'+str(len(data)//2)+'H',data))
 while value>>16:value=(value&0xffff)+(value>>16)
 return (~value)&0xffff
def owner_mac():
 p=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f367r9-f365-transition-observation-device-bound/openmitrastar-linux510-f367r9-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.dtb'
 data=p.read_bytes();_,total,start,strings,*_=struct.unpack_from('>10I',data);assert total==len(data)
 cursor=start;stack=[];addresses=[]
 while True:
  token=struct.unpack_from('>I',data,cursor)[0];cursor+=4
  if token==1:
   end=data.index(0,cursor);stack.append(data[cursor:end].decode());cursor=(end+4)&~3
  elif token==2:stack.pop()
  elif token==3:
   size,offset=struct.unpack_from('>II',data,cursor);cursor+=8;end=data.index(0,strings+offset);name=data[strings+offset:end].decode();value=data[cursor:cursor+size];cursor=(cursor+size+3)&~3
   if stack[-1]=='ethernet@e8000000' and name=='local-mac-address':addresses.append(value)
  elif token==4:pass
  elif token==9:break
  else:raise ValueError('DT token')
 assert len(addresses)==1 and len(addresses[0])==6
 mac=bytearray(addresses[0]);assert not mac[0]&1 and mac[0]<=253;mac[0]+=2;return bytes(mac)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--target',choices=['192.168.1.90','192.168.1.91'],default='192.168.1.91');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 pc=subprocess.check_output(['pwsh.exe','-NoProfile','-Command',"(Get-NetAdapter -InterfaceIndex 16).MacAddress"],text=True).strip()
 src=bytes.fromhex(pc.replace('-',''));dst=owner_mac();assert len(src)==len(dst)==6
 dll=c.CDLL('C:/Windows/System32/Npcap/wpcap.dll')
 dll.pcap_open_live.argtypes=[c.c_char_p,c.c_int,c.c_int,c.c_int,c.c_char_p];dll.pcap_open_live.restype=c.c_void_p
 dll.pcap_compile.argtypes=[c.c_void_p,c.POINTER(types.bpf),c.c_char_p,c.c_int,c.c_uint];dll.pcap_compile.restype=c.c_int
 dll.pcap_setfilter.argtypes=[c.c_void_p,c.POINTER(types.bpf)];dll.pcap_setfilter.restype=c.c_int
 dll.pcap_next_ex.argtypes=[c.c_void_p,c.POINTER(c.POINTER(types.header)),c.POINTER(c.POINTER(c.c_ubyte))];dll.pcap_next_ex.restype=c.c_int
 dll.pcap_sendpacket.argtypes=[c.c_void_p,c.c_char_p,c.c_int];dll.pcap_sendpacket.restype=c.c_int
 dll.pcap_close.argtypes=[c.c_void_p];dll.pcap_freecode.argtypes=[c.POINTER(types.bpf)]
 err=c.create_string_buffer(256);handle=dll.pcap_open_live(b'\\Device\\NPF_{B75315D5-9F01-448F-A259-C9D8F25D2233}',256,0,100,err)
 if not handle:raise RuntimeError(err.value.decode(errors='replace'))
 payload=secrets.token_bytes(64);ident=int.from_bytes(secrets.token_bytes(2),'big');sent=received=0;replies=[]
 try:
  program=types.bpf();rule=('icmp and src host '+a.target+' and dst host 192.168.1.49').encode()
  assert dll.pcap_compile(handle,c.byref(program),rule,1,0xffffffff)==0
  assert dll.pcap_setfilter(handle,c.byref(program))==0;dll.pcap_freecode(c.byref(program))
  for sequence in range(5):
   icmp=struct.pack('>BBHHH',8,0,0,ident,sequence)+payload;icmp=icmp[:2]+struct.pack('>H',checksum(icmp))+icmp[4:]
   ip=struct.pack('>BBHHHBBH4s4s',0x45,0,20+len(icmp),ident,0,64,1,0,socket.inet_aton('192.168.1.49'),socket.inet_aton(a.target))
   ip=ip[:10]+struct.pack('>H',checksum(ip))+ip[12:];frame=dst+src+b'\x08\x00'+ip+icmp
   assert dll.pcap_sendpacket(handle,frame,len(frame))==0;sent+=1;deadline=time.monotonic()+1.2
   while time.monotonic()<deadline:
    hp=c.POINTER(types.header)();dp=c.POINTER(c.c_ubyte)();rc=dll.pcap_next_ex(handle,c.byref(hp),c.byref(dp))
    if rc==0:continue
    if rc<0:raise RuntimeError('pcap receive failure')
    packet=c.string_at(dp,hp.contents.caplen)
    if len(packet)<42 or packet[12:14]!=b'\x08\x00':continue
    ihl=(packet[14]&15)*4;body=packet[14+ihl:]
    if len(body)<8:continue
    reply_type,code,sumv,rx_ident,rx_seq=struct.unpack_from('>BBHHH',body)
    if reply_type==0 and code==0 and rx_ident==ident and rx_seq==sequence and body[8:]==payload:
     received+=1;replies.append({'sequence':sequence,'ttl':packet[22],'source_mac_matches_expected':packet[6:12]==dst,'icmp_checksum_valid':checksum(body)==0});break
  report={'schema':'openmitrastar.eth73-finite-raw-icmp/v1','target':a.target+' eth1','frames_sent':sent,'echo_replies':received,
   'payload_bytes':64,'payload_sha256':hashlib.sha256(payload).hexdigest(),'target_mac_sha256':hashlib.sha256(dst).hexdigest(),
   'arp_lookup_used':False,'host_neighbor_changed':False,'raw_packets_saved':False,'replies':replies,'router_rebooted':False,'flash_writes':0,'bootenv_writes':0}
  (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 finally:dll.pcap_close(handle)
if __name__=='__main__':main()
