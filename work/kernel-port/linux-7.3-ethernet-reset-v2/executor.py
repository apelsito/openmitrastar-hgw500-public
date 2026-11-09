"""Owner-authorized one-shot ETH73 RAM trial. No flash or persistent bootenv.
Retains existing continuous UART receiver, lease and receiver-driven YMODEM.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,socket,subprocess,sys,threading,time,zlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PREVIOUS=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/basic73-ram-executor-v5'
spec=importlib.util.spec_from_file_location('basic73_transport',PREVIOUS/'executor.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
PROMPT=rb'eth73>\s*$';KERNEL=b'7.3.0-openmitrastar-eth73-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def preflight(config):
 data=Path(config['image']).read_bytes();m.require(len(data)==config['bytes'] and sha(config['image'])==config['sha256'],'image identity drift')
 m.require(f'{zlib.crc32(data)&0xffffffff:08x}'==config['crc32'],'image CRC drift')
 sys.path.insert(0,str(ROOT/'tools'));from bootbase_contract_emulator import validate_bootbase_slot
 contract=validate_bootbase_slot('ETH73-RAM-ONLY',data,0x1000000)
 m.require(contract.accepted_by_contract and contract.header['load']=='0x8493a000' and contract.header['entry']==config['entry'] and contract.header['compression']==0,'Bootbase contract refused')
 m.require(len(data[8192:])==config['payload_bytes'] and hashlib.sha256(data[8192:]).hexdigest()==config['raw_sha256'],'payload changed')
 m.require(0x83000000+len(data)<0x84000000 and 0x8493a000+config['payload_bytes']<0x88000000,'RAM interval overlap')
 return dict(path=config['image'],bytes=len(data),sha256=config['sha256'],crc32=config['crc32'])
class Log(m.RedactedLog):
 def line(self,line):
  sensitive=re.search(rb'(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|psk|password|calibration|ssid|token_enc',line)
  allowed=re.search(rb'^(?:Linux version |OPENMITRASTAR_|ETH73_|ETH[01]_|ETHLOAD|UDP_|OMEMAC |F352 |descriptor DDR |qtn_topaz_emac_eth73 |7\.3\.0-openmitrastar-|memtest |Topaz BASIC UART0 IRQ:|bootcmd=|bootselect=|filesize=|[0-9a-f]{8}:|Verifying Checksum|Total Size|Bytes transferred|\d+\.\d+ \d+\.\d+|\s*\d+:|\s*(?:eth[01]|lo):|irq|napi|poll|rx_|dma_|cur_rx|schema=|Bootbase Version|U-Boot |Info: Quantenna U-Boot|Hit any key|=>Hit any key|topaz>|ZHAL>|## |Kernel panic|Oops:|BUG:|Fatal exception|ETH73ATTACH-|qtn-topaz-emac-eth73 |ETH[01]_ADDR|ETH[01]_FLAGS|stop_reset_|[01]$|up$|down$|READ_ERROR|NET_[A-Z]+|\s*[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+|Iface)',line)
  if sensitive or not allowed:self.omitted+=1;return
  with self.path.open('ab') as f:f.write(line[:1024]+b'\n')
  self.lines+=1
class Backend(m.WindowsBackend):
 def lease(self):
  if time.monotonic()-self.last_lease<2:return
  p=self.args;r=subprocess.run(['pwsh.exe','-NoProfile','-File',str(HERE/'assert_lease.ps1'),'-PhysicalLockDir',p.lock,'-OwnerPid',str(p.owner_pid),'-OwnerStartTicks',str(p.owner_ticks),'-LeaseToken',p.lease_token],capture_output=True,timeout=20)
  m.require(r.returncode==0 and b'BASIC73_LEASE_PASS' in r.stdout,'ETH73 parent lease invalid');self.last_lease=time.monotonic()
 def ssh(self,*args,**kwargs):raise m.Refusal('SSH absent from this RAM diagnosis')
 def reboot_once(self):raise m.Refusal('Initial reset is owner power-cycle; no reboot syscall')
class Flow(m.Flow):
 def __init__(self,*args,config,output,**kwargs):super().__init__(*args,**kwargs);self.config=config;self.output=output;self.traffic=[]
 def wait(self,pattern,seconds):
  # Parent owns the device and monitors the lease continuously. Spawning a
  # PowerShell process between received bytes can overrun the modem timeout.
  deadline=self.clock()+seconds;data=bytearray()
  while self.clock()<deadline:
   self.safe();data+=self.s.read(size=1,timeout=min(.1,max(.001,deadline-self.clock())))
   m.require(len(data)<=262144,'response exceeds bounded window')
   m.require(not re.search(m.FATAL,data),'fatal UART marker')
   if re.search(pattern,data):return bytes(data)
  raise TimeoutError('UART stage expired')
 def command(self,command,prompt=PROMPT,seconds=25):
  allowed=m.ALLOWED|{'printenv bootcmd bootselect','ethload','modules','eth0up','eth0down','eth1up','eth1down','status','interrupts','netstats','ethstats','eth1stats','netdiag','eth0state','eth1state','cpuinfo','memtest','udpecho'}
  allowed.add(f"crc32 83000000 {self.config['bytes']:08x} 84000000")
  m.require(command in allowed or re.fullmatch(r'echo [A-Za-z0-9-]{1,40}',command),'command outside RAM test allowlist')
  self.safe();self.b.force_lease();self.fresh();self.s.write(command.encode()+(b'\r' if prompt==m.PROMPT else b'\n'),timeout=3)
  r=self.wait(prompt,seconds);self.steps.append(command);return r
 def verify_ram(self):
  size=self.command('printenv filesize',m.PROMPT)
  rows=re.findall(rb'(?mi)^filesize=([0-9a-f]+)\r?$',size);m.require(len(rows)==1 and int(rows[0],16)==self.config['bytes'],'physical filesize mismatch')
  info=self.command('iminfo 83000000',m.PROMPT,60)
  m.require(b'Verifying Checksum ... OK' in info and not re.search(rb'(?i)bad.*crc|bad.*checksum',info),'iminfo checksum refusal')
  for label,v in [('Load Address','8493a000'),('Entry Point',self.config['entry'][2:])]:m.require(re.search(label.encode()+rb':\s*(?:0x)?'+v.encode()+rb'(?:\s|$)',info,re.I),'iminfo addresses differ')
  m.require(re.search(rb'Data Size:\s*'+str(self.config['payload_bytes']).encode()+rb'(?:\s|$)',info),'payload size differs')
  m.require(re.search(rb'Image Type:[^\r\n]*(?:uncompressed|compression none)',info,re.I),'compression differs')
  self.command(f"crc32 83000000 {self.config['bytes']:08x} 84000000",m.PROMPT,90)
  m.require(m.parse_word(self.command('md.l 84000000 1',m.PROMPT),'84000000')==self.config['crc32'],'physical RAM CRC mismatch')
 def catch_topaz_fast(self,ready=None):
  # Parent owns the mutex and continuously validates its lease. No process
  # creation on the timing-critical stop key. RX errors remain latched.
  deadline=self.clock()+60;data=bytearray();seen=set();escaped=False
  while self.clock()<deadline:
   self.safe()
   if ready:ready.set()
   data+=self.s.read(timeout=.05);m.require(len(data)<=262144,'boot capture exceeds bound')
   if re.search(m.PROMPT,data):self.steps.append('fresh Topaz captured');return bytes(data)
   for match in re.finditer(rb'Hit any key to stop autoboot|Hit any key to exit|ZHAL>',data):
    key=(match.start(),bytes(match.group()))
    if key in seen:continue
    seen.add(key);self.safe()
    if match.group()==b'ZHAL>':
     m.require(not escaped,'duplicate BootExtension prompt');escaped=True;self.s.write(b'\x15\x08ATGU\r',timeout=3)
    else:self.s.write(b' ',timeout=3)
  raise TimeoutError('fresh Bootbase not caught after authorized reboot')
 def run(self):
  preflight(self.config);self.b.force_lease();self.fresh()
  # Fresh input on the currently-running ETH73 unit before manual restart.
  nonce=self.command('echo '+self.nonce)
  m.require(re.findall(rb'(?m)^ETH73_NONCE=([^\r\n]+)\r?$',nonce)==[self.nonce.encode()],'Current ETH73 UART identity mismatch')
  m.require(KERNEL in self.command('status'),'Current ETH73 kernel differs')
  (self.output/'READY_POWER_CYCLE.json').write_text(json.dumps({'status':'CAPTURE_READY_OWNER_POWER_CYCLE','pnp_verified':True,'fresh_eth73_uart_nonce':True,'flash_writes':0,'bootenv_writes':0})+'\n')
  print('ETH73_RESET_CAPTURE_READY_POWER_CYCLE_NOW',flush=True)
  deadline=self.clock()+600
  while self.clock()<deadline:
   try:self.catch_topaz_fast();break
   except TimeoutError:continue
  else:raise TimeoutError('new owner power-cycle not received')
  m.parse_environment(self.command('printenv bootcmd bootselect',m.PROMPT))
  for address in ['e0000004','f4000000']:
   value=m.parse_word(self.command('md.l '+address+' 1',m.PROMPT),address)
   m.require(int(value,16)&((1<<29)|(1<<30))==0 if address=='e0000004' else value=='00000000','map/watchdog not qualified')
  self.b.force_lease();self.fresh();self.s.write(b'loady 83000000\r',timeout=3);self.wait(m.LOADY_READY,20)
  import f323_uart_ymodem_load as f323;import uart_ymodem_load as original
  recorder=f323.ControlEventRecorder()
  # Parent holds and verifies the lease every second; no process creation
  # between timing-sensitive bytes. Continuous RX still latches fatal/error.
  transfer_started=time.monotonic();control_stream=(self.output/'transfer-timing.jsonl').open('x',buffering=1)
  def record(kind,**values):control_stream.write(json.dumps({'kind':kind,'seconds':round(time.monotonic()-transfer_started,4),**values})+'\n')
  def rx(size,timeout):
   self.safe();start=time.monotonic();data=self.s.read(size=size,timeout=timeout)
   record('rx',bytes=len(data),control=data.hex() if len(data)==1 else None,elapsed=round(time.monotonic()-start,4));return data
  def tx(data,timeout):
   self.safe();start=time.monotonic();written=self.s.write(data,timeout=timeout)
   record('tx',bytes=written,elapsed=round(time.monotonic()-start,4));return written
  modem=f323.F323ModemSocket(rx,tx,packet_size=1024,protocol_type=original.ProtocolType.YMODEM,recorder=recorder)
  last=[-10]
  def progress(index,name,total,success):
   percent=int(success*100/total) if total else 0
   if percent>=last[0]+1 or success==total:record('progress',acked_bytes=success,total=total,percent=percent)
   if percent>=last[0]+10 or success==total:last[0]=percent;print('ETH73_YMODEM='+str(percent)+' bytes='+str(success),flush=True)
  outcome='failed'
  try:m.require(modem.send([self.config['image']],progress),'YMODEM failed');outcome='completed'
  finally:recorder.write_result(self.output/'ymodem-control-events.json',outcome);control_stream.close()
  self.wait(m.PROMPT,60);self.verify_ram();preflight(self.config)
  m.require(int(m.parse_word(self.command('md.l e0000004 1',m.PROMPT),'e0000004'),16)&((1<<29)|(1<<30))==0,'legacy map changed')
  m.require(m.parse_word(self.command('md.l f4000000 1',m.PROMPT),'f4000000')=='00000000','watchdog changed')
  self.b.force_lease();self.fresh();self.boots+=1;self.s.write(b'bootm 83000000\r',timeout=3)
  boot=self.wait(PROMPT,120);m.require(b'Linux version '+KERNEL in boot and b'OPENMITRASTAR_ETH73_PID1_REACHED' in boot,'ETH73 kernel/PID1 not received')
  nonce=self.command('echo '+self.nonce);m.require(re.findall(rb'(?m)^ETH73_NONCE=([^\r\n]+)\r?$',nonce)==[self.nonce.encode()],'ETH73 interactive nonce mismatch')
  first=self.command('status');up1=float(re.search(rb'(?m)^(\d+\.\d+) \d+\.\d+\r?$',first)[1])
  m.require(b'memtest PASS 1MiB two patterns' in self.command('memtest',seconds=30),'memtest failed')
  m.require(re.search(rb'(?m)^ETHLOAD=0\r?$',self.command('ethload',seconds=45)),'driver load failed')
  m.require(b'qtn_topaz_emac_eth73 ' in self.command('modules'),'module not listed')
  diag=self.command('netdiag');(self.output/'network-address-diag.txt').write_bytes(diag)
  # Owner moved the cable to the second connector; leave eth0 down throughout.
  for command in ['eth1up','eth1down','eth1up']:
   result=self.command(command,seconds=35)
   m.require((b'ETH1_UP=0' if command.endswith('up') else b'ETH1_DOWN=0') in result,'Second port lifecycle failed')
  diag=self.command('netdiag');(self.output/'network-address-diag-after.txt').write_bytes(diag)
  self.command('eth1state')
  before=self.command('interrupts');self.command('eth1stats');netbefore=self.command('netstats')
  ping=subprocess.run(['C:/Windows/System32/ping.exe','-n','3','-w','1500','192.168.1.91'],capture_output=True,timeout=12)
  ping_ok=ping.returncode==0 and b'TTL=' in ping.stdout
  self.s.write(b'udpecho\n',timeout=3);self.wait(rb'UDP_READY_PORT9009\r?\n',15)
  sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('192.168.1.49',0));sock.settimeout(1.0)
  echoed=0
  try:
   for i in range(12):
    payload=('ETH73-'+self.nonce+'-'+str(i)).encode();sock.sendto(payload,('192.168.1.91',9009))
    try:data,address=sock.recvfrom(512);echoed+=int(data==payload and address==('192.168.1.91',9009))
    except socket.timeout:pass
    self.safe();self.b.lease()
  finally:sock.close()
  udp=self.wait(PROMPT,20);netafter=self.command('netstats');irqafter=self.command('interrupts');self.command('eth1stats')
  second=self.command('status');up2=float(re.search(rb'(?m)^(\d+\.\d+) \d+\.\d+\r?$',second)[1]);m.require(up2>up1,'uptime not increasing')
  m.require(b'UDP_RECEIVED=' in udp and b'UDP_ECHOED=' in udp,'UDP accounting absent')
  (self.output/'network-counters.json').write_text(json.dumps({'before':netbefore.decode(errors='replace'),'after':netafter.decode(errors='replace'),'irq_before':before.decode(errors='replace'),'irq_after':irqafter.decode(errors='replace')},indent=2)+'\n')
  return {'status':'PASS_ETH73_PHYSICAL_BOOT_DRIVER_AND_TRAFFIC' if ping_ok and echoed>=8 else 'BOOT_DRIVER_PASS_TRAFFIC_INCOMPLETE','reboots':self.reboots,'bootm':self.boots,'steps':self.steps,'ping_pass':ping_ok,'udp_echoes':echoed,'udp_attempts':12,'uptime_first':up1,'uptime_second':up2,'runtime':'ETH73_RESET_RAM_ETH1_UP_ETH0_DOWN','ethernet_physical_port_mapping':'UNRUN','long_soak':'UNRUN','persistent_boot':'UNRUN'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token');p.add_argument('--baseline-boot',default='');p.add_argument('--attach-receiver',action='store_true');p.add_argument('--wait-power-cycle',action='store_true');a=p.parse_args()
 config=json.loads(a.config.read_text());artifact=preflight(config)
 if not a.execute:print(json.dumps({'status':'OFFLINE_PREFLIGHT_PASS','artifact':artifact}));return
 a.output.mkdir(exist_ok=False);log=Log(a.output/'uart-redacted.txt');session=flow=None
 result={'status':'STOP_RAM_TRIAL','artifact':artifact,'flash_writes':0,'bootenv_writes':0,'raw_uart_saved':False}
 try:
  backend=Backend(a);backend.force_lease();session=m.continuous_session(log,backend)
  flow=Flow(backend,session,hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32],config=config,output=a.output)
  result.update(flow.run())
 except BaseException as e:result.update(error_type=type(e).__name__,error_reason=str(e),steps=flow.steps if flow else [],bootm=flow.boots if flow else 0,reboots=flow.reboots if flow else 0);print('ETH73_STOP '+str(e),flush=True);raise
 finally:
  if session:session.close()
  result.update(redacted_lines=log.lines,omitted_lines=log.omitted)
  (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
