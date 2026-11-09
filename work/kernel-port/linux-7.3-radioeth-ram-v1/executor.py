"""One owner-authorized RAM boot of the exact combined radio/Ethernet image.

Local UART/YMODEM; no flash/bootenv, cleartext service or automatic AP start.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,socket,ssl,time,urllib.request,zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('retained_reset_transport',HERE.parent/'linux-7.3-ethernet-reset-v2/executor.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE=m.m
PROMPT=rb'eth73>\s*$'
KERNEL=b'7.3.0-openmitrastar-radio73-v1'
OLD_KERNEL=b'7.3.0-openmitrastar-eth73-v1'
COMMANDS={'status','interrupts','meminfo','memtest','cpuinfo','ethload','modules','eth0up','eth0down','eth1up','eth1down','netstats','ethstats','eth1stats','eth0txdiag','eth1txdiag','eth0state','eth1state','netdiag','pcistatus','radioload','radiostatus','radioes','userlandtest','httpsstart','sshstart'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def preflight(config):
 artifact=m.preflight(config)
 BASE.require(config['kernel_release']==KERNEL.decode(),'kernel marker differs')
 BASE.require(config['classification']=='RAM_DIAGNOSTIC_NO_FLASH','flash artifact outside this executor')
 BASE.require(sha(config['tls_cert'])==config['tls_cert_sha256'],'TLS trust anchor changed')
 BASE.require(sha(config['receipt'])==config['receipt_sha256'],'paired receipt changed')
 receipt=json.loads(Path(config['receipt']).read_text())
 BASE.require(receipt['status']=='PASS_PAIRED_RAM_BUILD_PHYSICAL_UNRUN' and receipt['lanes'][0]['image_sha256']==config['sha256'],'build receipt does not bind image')
 return artifact

class Log(m.Log):
 def line(self,line):
  # Radio tools can print client MAC/SSID. Unknown lines remain omitted.
  if re.search(rb'(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|psk|password|calibration|ssid|private.key|token_enc',line):self.omitted+=1;return
  if re.search(rb'^(?:RADIO_|RADIOLOAD_|PCI_DEVICE|WIPHY_PRESENT|CHILD_|USERLAND_TEST_|SHELL_ARITH_PASS|0x[0-9a-f]+$|phy#|Interface wlan|type |channel |country ES:|mac_|tx_|txp_|debug_selector|active_speed|full_duplex|max_frame|pause_time|rxp_|[0-9]{9,}$|iw version)',line):
   with self.path.open('ab') as f:f.write(line[:1024]+b'\n')
   self.lines+=1;return
  super().line(line)

class Flow(m.Flow):
 def wait(self,pattern,seconds):
  deadline=self.clock()+seconds;data=bytearray()
  while self.clock()<deadline:
   self.safe();data+=self.s.read(size=1,timeout=min(.1,max(.001,deadline-self.clock())))
   BASE.require(len(data)<=262144,'bounded UART window exceeded')
   BASE.require(not re.search(BASE.FATAL,data),'fatal UART marker')
   if re.search(pattern,data):return bytes(data)
  raise TimeoutError('UART stage expired')
 def command(self,command,prompt=PROMPT,seconds=30):
  allowed=COMMANDS|BASE.ALLOWED|{'printenv bootcmd bootselect',f"crc32 83000000 {self.config['bytes']:08x} 84000000"}
  BASE.require(command in allowed or re.fullmatch(r'echo [A-Za-z0-9-]{1,40}',command),'command outside RAM allowlist')
  self.safe();self.b.force_lease();self.fresh();self.s.write(command.encode()+(b'\r' if prompt==BASE.PROMPT else b'\n'),timeout=3)
  # Bootbase can prefix the command echo with topaz>; require a quiet final
  # prompt after the response. Linux background logs need no global quiet.
  if prompt==BASE.PROMPT:
   deadline=self.clock()+seconds;data=bytearray();quiet=None
   while self.clock()<deadline:
    self.safe();chunk=self.s.read(size=4096,timeout=.05)
    if chunk:data+=chunk;quiet=None
    elif re.search(prompt,data):
     quiet=quiet or self.clock()
     if self.clock()-quiet>=.15:self.steps.append(command);return bytes(data)
    BASE.require(len(data)<=262144 and not re.search(BASE.FATAL,data),'unsafe Bootbase response')
   raise TimeoutError('Complete Bootbase reply not received')
  response=self.wait(prompt,seconds);self.steps.append(command);return response
 def synchronize_nonce(self,kernel):
  self.fresh();self.s.write(b'\n',timeout=3)
  deadline=self.clock()+2
  while self.clock()<deadline:
   self.safe()
   if b'eth73>' in self.s.read(4096,.05):break
  nonce=self.command('echo '+self.nonce)
  BASE.require(re.search(rb'(?m)^ETH73_NONCE='+self.nonce.encode()+rb'\r?$',nonce),'fresh console nonce missing')
  status=self.command('status')
  BASE.require(re.search(rb'(?m)^'+re.escape(kernel)+rb'\r?$',status),'kernel identity differs')
  return status
 def run(self):
  preflight(self.config);self.b.force_lease();self.synchronize_nonce(OLD_KERNEL)
  (self.output/'READY_POWER_CYCLE.json').write_text(json.dumps({'status':'CAPTURE_READY_OWNER_POWER_CYCLE','fresh_uart_nonce':True,'artifact_sha256':self.config['sha256'],'flash_writes':0,'bootenv_writes':0})+'\n')
  print('RADIOETH73_CAPTURE_READY_POWER_CYCLE_NOW',flush=True)
  # Real continuous catcher is now active; no lease subprocess between bytes.
  deadline=self.clock()+600
  while self.clock()<deadline:
   try:self.catch_topaz_fast();break
   except TimeoutError:continue
  else:raise TimeoutError('Owner power-cycle not received')
  BASE.parse_environment(self.command('printenv bootcmd bootselect',BASE.PROMPT))
  for address in ['e0000004','f4000000']:
   value=BASE.parse_word(self.command('md.l '+address+' 1',BASE.PROMPT),address)
   BASE.require(int(value,16)&((1<<29)|(1<<30))==0 if address=='e0000004' else value=='00000000','unqualified map/watchdog')
  self.b.force_lease();self.fresh();self.s.write(b'loady 83000000\r',timeout=3);self.wait(BASE.LOADY_READY,20)
  import f323_uart_ymodem_load as f323
  import uart_ymodem_load as original
  recorder=f323.ControlEventRecorder();started=time.monotonic()
  modem=f323.F323ModemSocket(lambda size,timeout:(self.safe(),self.s.read(size=size,timeout=timeout))[1],lambda data,timeout:(self.safe(),self.s.write(data,timeout=timeout))[1],packet_size=1024,protocol_type=original.ProtocolType.YMODEM,recorder=recorder)
  last=[-10]
  def progress(index,name,total,success):
   percent=int(success*100/total) if total else 0
   if percent>=last[0]+10 or success==total:
    last[0]=percent;print('RADIOETH73_YMODEM='+str(percent)+' bytes='+str(success),flush=True)
  outcome='failed'
  try:BASE.require(modem.send([self.config['image']],progress),'YMODEM incomplete');outcome='completed'
  finally:recorder.write_result(self.output/'ymodem-control-events.json',outcome)
  self.wait(BASE.PROMPT,60);self.verify_ram();preflight(self.config)
  BASE.require(int(BASE.parse_word(self.command('md.l e0000004 1',BASE.PROMPT),'e0000004'),16)&((1<<29)|(1<<30))==0,'legacy map changed')
  BASE.require(BASE.parse_word(self.command('md.l f4000000 1',BASE.PROMPT),'f4000000')=='00000000','watchdog changed')
  self.b.force_lease();self.fresh();self.boots+=1;self.s.write(b'bootm 83000000\r',timeout=3)
  boot=self.wait(PROMPT,180)
  BASE.require(b'Linux version '+KERNEL in boot and b'OPENMITRASTAR_RADIOETH73_RAM_V1' in boot,'new kernel/PID1 absent')
  first=self.synchronize_nonce(KERNEL)
  BASE.require(b'memtest PASS 1MiB two patterns' in self.command('memtest',seconds=35),'memtest failed')
  self.command('userlandtest',seconds=45)
  BASE.require(b'ETHLOAD=0' in self.command('ethload',seconds=45),'Ethernet load failed')
  results={}
  for name in ['pcistatus','modules','eth0state','eth1state']:results[name]=self.command(name,seconds=45).decode(errors='replace')
  for name in ['eth1up','eth1txdiag','eth1stats','eth1state']:
   results[name]=self.command(name,seconds=45).decode(errors='replace')
  # Probe radio without starting an AP; preserve explicit control boundaries.
  radio=self.command('radioload',seconds=120);results['radio_load_shape']={'complete':b'RADIOLOAD_MODULES_COMPLETE' in radio,'successes':len(re.findall(rb'RADIO_MODULE_RESULT=0\r?\n',radio)),'sha256':hashlib.sha256(radio).hexdigest()}
  results['pci_after_radio']=self.command('pcistatus',seconds=45).decode(errors='replace')
  results['https_start']=self.command('httpsstart',seconds=45).decode(errors='replace')
  # HTTPS test endpoint is a known finite binary and certificate is verified.
  context=ssl.create_default_context(cafile=self.config['tls_cert'])
  url='https://192.168.1.91/__traffic.bin';traffic={'attempts':3,'exact':0,'tls_versions':[]}
  for _ in range(3):
   try:
    with urllib.request.urlopen(url,context=context,timeout=12) as response:
     body=response.read(65537);traffic['exact']+=int(body==bytes(range(256))*256)
   except (OSError,TimeoutError) as error:traffic['last_error_type']=type(error).__name__
  results['eth1_https_traffic']=traffic
  for name in ['eth1txdiag','eth1stats','netstats','interrupts','status']:results['after_'+name]=self.command(name,seconds=45).decode(errors='replace')
  (self.output/'gates.json').write_text(json.dumps(results,indent=2)+'\n')
  return {'status':'PASS_RAM_BOOT_RADIO_PROBE_ETH1_HTTPS' if traffic['exact']==3 and results['radio_load_shape']['complete'] else 'RAM_BOOT_PASS_REMAINING_GATES_INCOMPLETE','bootm':self.boots,'reboots':0,'steps':self.steps,'transfer_seconds':time.monotonic()-started,'gates':results,'eth0_traffic':'UNRUN','wifi_client':'UNRUN','persistent':'UNRUN','flash_writes':0,'bootenv_writes':0}

def main():
 p=argparse.ArgumentParser()
 for name in ['config','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--execute',action='store_true');p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token');p.add_argument('--baseline-boot',default='')
 a=p.parse_args();config=json.loads(a.config.read_text());artifact=preflight(config)
 if not a.execute:print(json.dumps({'status':'PASS_EXACT_RAM_PREFLIGHT','artifact':artifact}));return
 a.output.mkdir(exist_ok=False);log=Log(a.output/'uart-redacted.txt');session=flow=None
 result={'status':'STOP_RAM_TRIAL','artifact':artifact,'flash_writes':0,'bootenv_writes':0}
 try:
  backend=m.Backend(a);backend.force_lease();session=BASE.continuous_session(log,backend)
  flow=Flow(backend,session,hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32],config=config,output=a.output)
  result.update(flow.run())
 except BaseException as error:
  result.update(error_type=type(error).__name__,error_reason=str(error),steps=flow.steps if flow else [],bootm=flow.boots if flow else 0);print('RADIOETH73_STOP '+str(error),flush=True);raise
 finally:
  if session:session.close()
  result.update(redacted_lines=log.lines,omitted_lines=log.omitted,raw_uart_saved=False)
  (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
