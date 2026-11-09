"""Load the exact events image after the owner cycles the halted RAM unit.

Owner power-cycle only; no software reset, flash or environment writes. Fresh guard, receiver/prompt proof,
explicit overlapped write deadlines, full CRC then exactly one kernel handoff.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('radioeth_v1',SOURCE/'executor.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter


def preflight(config):
 image=Path(config['image']).read_bytes()
 m.BASE.require(len(image)==config['bytes'] and m.sha(config['image'])==config['sha256'],'exact image changed')
 import zlib,lzma
 m.BASE.require(f'{zlib.crc32(image)&0xffffffff:08x}'==config['crc32'],'image CRC changed')
 sys.path.insert(0,str(ROOT/'tools'))
 from bootbase_contract_emulator import validate_bootbase_slot
 contract=validate_bootbase_slot('AUTOSTART2G-RAM-test',image,0x5e0000)
 m.BASE.require(contract.accepted_by_contract and contract.header['entry']==config['entry'] and contract.header['load']=='0x8493a000' and contract.header['compression']==3,'Bootbase contract changed')
 decoded=lzma.decompress(image[8192:],format=lzma.FORMAT_ALONE)
 m.BASE.require(len(decoded)==config['raw_bytes'] and hashlib.sha256(decoded).hexdigest()==config['raw_sha256'],'decoded kernel drift')
 m.BASE.require(0x83000000+len(image)<0x84000000 and 0x8493a000+len(decoded)<0x88000000,'RAM interval contract')
 m.BASE.require(config['classification']=='FLASH_CANDIDATE_NEEDS_RAM_BOOT_READBACK_ROLLBACK','wrong scope')
 m.BASE.require(config['kernel_release']==m.KERNEL.decode(),'kernel release changed')
 for key in ['receipt','qualification','tls_cert']:
  m.BASE.require(m.sha(config[key])==config[key+'_sha256'],'proof/trust input changed')
 build=json.loads(Path(config['receipt']).read_text())
 qualification=json.loads(Path(config['qualification']).read_text())
 m.BASE.require(build['status']=='PASS_PAIRED_2G_DOOM_FLASH_CANDIDATE_PHYSICAL_UNRUN' and build['lanes'][0]['image_sha256']==config['sha256'],'paired build does not bind image')
 m.BASE.require(qualification['status']=='PASS_INDEPENDENT_2G_FLATCPIO_LZMA_ENTRY_PREFIX_ROOT_CONTRACTS' and qualification['build_result_sha256']==config['receipt_sha256'],'qualification mismatch')
 return {'path':config['image'],'bytes':config['bytes'],'sha256':config['sha256'],'crc32':config['crc32']}

class Flow(m.Flow):

 def verify_ram(self):
  size=self.command('printenv filesize',m.BASE.PROMPT)
  rows=re.findall(rb'(?mi)^filesize=([0-9a-f]+)\r?$',size)
  m.BASE.require(len(rows)==1 and int(rows[0],16)==self.config['bytes'],'physical filesize differs')
  info=self.command('iminfo 83000000',m.BASE.PROMPT,60)
  m.BASE.require(b'Verifying Checksum ... OK' in info and not re.search(rb'(?i)bad.*crc|bad.*checksum',info),'iminfo checksum refused')
  for label,value in [('Load Address','8493a000'),('Entry Point',self.config['entry'][2:])]:
   m.BASE.require(re.search(label.encode()+rb':\s*(?:0x)?'+value.encode()+rb'(?:\s|$)',info,re.I),'physical load/entry differs')
  m.BASE.require(re.search(rb'Data Size:\s*'+str(self.config['payload_bytes']).encode()+rb'(?:\s|$)',info),'payload size differs')
  m.BASE.require(re.search(rb'Image Type:[^\r\n]*lzma',info,re.I),'physical compression differs')
  self.command(f"crc32 83000000 {self.config['bytes']:08x} 84000000",m.BASE.PROMPT,90)
  m.BASE.require(m.BASE.parse_word(self.command('md.l 84000000 1',m.BASE.PROMPT),'84000000')==self.config['crc32'],'physical RAM CRC mismatch')
 def run(self):
  preflight(self.config);self.b.force_lease();self.fresh()
  self.synchronize_nonce(m.KERNEL)
  (self.output/'READY_POWER_CYCLE.json').write_text(json.dumps({'status':'CAPTURE_READY_OWNER_POWER_CYCLE','artifact_sha256':self.config['sha256'],'flash_writes':0,'bootenv_writes':0,'fresh_current_kernel_nonce':True})+'\n')
  print('RADIO73_AUTOSTART_CAPTURE_READY_POWER_CYCLE_NOW',flush=True)
  deadline=self.clock()+600
  while self.clock()<deadline:
   try:self.catch_topaz_fast();break
   except TimeoutError:continue
  else:raise TimeoutError('Owner power-cycle not received')
  marker='RADIOETH73-ATTACH-'+self.nonce[:16]
  response=self.command('echo '+marker,m.BASE.PROMPT)
  m.BASE.require(re.search(rb'(?m)^'+marker.encode()+rb'\r?$',response),'Fresh Bootbase nonce absent')
  m.BASE.parse_environment(self.command('printenv bootcmd bootselect',m.BASE.PROMPT))
  for address in ['e0000004','f4000000']:
   value=m.BASE.parse_word(self.command('md.l '+address+' 1',m.BASE.PROMPT),address)
   m.BASE.require(int(value,16)&((1<<29)|(1<<30))==0 if address=='e0000004' else value=='00000000','unqualified map/watchdog')
  self.b.force_lease();self.fresh();self.s.write(b'loady 83000000\r',timeout=3);self.wait(m.BASE.LOADY_READY,20)
  import f323_uart_ymodem_load as f323
  import uart_ymodem_load as original
  recorder=f323.ControlEventRecorder();start=time.monotonic();deadline=start+1500
  telemetry=(self.output/'transfer-progress.jsonl').open('x',buffering=1)
  def record(kind,**extra):telemetry.write(json.dumps({'kind':kind,'elapsed':round(time.monotonic()-start,4),**extra})+'\n')
  def rx(size,timeout):
   self.safe();m.BASE.require(time.monotonic()<deadline,'transfer absolute deadline')
   data=self.s.read(size=size,timeout=timeout);record('rx',bytes=len(data),control=data.hex() if len(data)==1 else None);return data
  def tx(data,timeout):
   self.safe();m.BASE.require(time.monotonic()<deadline,'transfer absolute deadline')
   written=self.s.write(data,timeout=timeout);record('tx',bytes=written);return written
  modem=f323.F323ModemSocket(rx,tx,packet_size=1024,protocol_type=original.ProtocolType.YMODEM,recorder=recorder)
  percent=[-1];last_print=[-10]
  def progress(index,name,total,success):
   current=int(success*100/total) if total else 0
   if current!=percent[0]:percent[0]=current;record('progress',acked_bytes=success,total=total,percent=current)
   if current>=last_print[0]+10 or success==total:
    last_print[0]=current;print('RADIOETH73_YMODEM='+str(current)+' bytes='+str(success),flush=True)
  outcome='failed'
  try:m.BASE.require(modem.send([self.config['image']],progress),'YMODEM incomplete');outcome='completed'
  finally:recorder.write_result(self.output/'ymodem-control-events.json',outcome);telemetry.close()
  self.wait(m.BASE.PROMPT,60);self.verify_ram();preflight(self.config)
  for address in ['e0000004','f4000000']:
   value=m.BASE.parse_word(self.command('md.l '+address+' 1',m.BASE.PROMPT),address)
   m.BASE.require(int(value,16)&((1<<29)|(1<<30))==0 if address=='e0000004' else value=='00000000','map/watchdog changed before handoff')
  self.b.force_lease();self.fresh();self.boots+=1;self.s.write(b'bootm 83000000\r',timeout=3)
  boot=self.wait(m.PROMPT,180)
  m.BASE.require(b'Linux version '+m.KERNEL in boot,'new kernel absent')
  status=self.synchronize_nonce(m.KERNEL)
  m.BASE.require(b'memtest PASS 1MiB two patterns' in self.command('memtest',seconds=35),'memtest failed')
  userland=self.command('userlandtest',seconds=45)
  m.BASE.require(b'USERLAND_TEST_END' in userland and b'SHELL_ARITH_PASS' in userland,'Current userspace not executing correctly')
  m.BASE.require(b'OPENMITRASTAR_RADIOETH73_FLASH2G_R1' in boot and b'AUTOSTART_END' in boot,'new autostart image marker absent')
  m.BASE.require(b'AUTOSTART_ETH_FAILURE' not in boot and b'RADIOLOAD_STOP' not in boot,'automatic device startup failed')
  count=len(re.findall(rb'RADIO_MODULE_RESULT=0\r?\n',boot))
  m.BASE.require(count==19,'automatic radio module count incomplete')
  results={'kernel_status':status.decode(errors='replace'),'userland':userland.decode(errors='replace'),'radio_module_successes':count,'autostart_end':True}
  for name in ['modules','eth0state','eth1state','pcistatus']:
   results[name]=self.command(name,seconds=45).decode(errors='replace')
  (self.output/'gates.json').write_text(json.dumps(results,indent=2)+'\n')
  return {'status':'PASS_EXACT_2G_AUTOSTART_RAM_BOOT_19MODULES','bootm':self.boots,'reboots':0,'flash_writes':0,'bootenv_writes':0,'steps':self.steps,'gates':results,'ethernet_https_traffic':'UNRUN','wifi_client':'UNRUN','persistent':'UNRUN'}


def main():
 p=argparse.ArgumentParser()
 for name in ['config','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--execute',action='store_true');p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token');p.add_argument('--baseline-boot',default='')
 a=p.parse_args();config=json.loads(a.config.read_text());artifact=preflight(config)
 if not a.execute:print(json.dumps({'status':'PASS_SAME_IMAGE_RAM_RECOVERY_PREFLIGHT','artifact':artifact}));return
 a.output.mkdir(exist_ok=False);log=m.Log(a.output/'uart-redacted.txt');session=flow=None
 result={'status':'STOP_RAM_TRANSFER_RECOVERY','artifact':artifact,'flash_writes':0,'bootenv_writes':0,'reboots':0}
 try:
  backend=m.m.Backend(a);backend.force_lease();session=m.BASE.continuous_session(log,backend)
  writer=BoundedSerialWriter(session);session.write=writer.write
  flow=Flow(backend,session,hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32],config=config,output=a.output)
  result.update(flow.run())
 except BaseException as error:
  result.update(error_type=type(error).__name__,error_reason=str(error),steps=flow.steps if flow else [],bootm=flow.boots if flow else 0,reboots=0);print('RADIOETH73_STOP '+str(error),flush=True);raise
 finally:
  if session:session.close()
  result.update(redacted_lines=log.lines,omitted_lines=log.omitted,raw_uart_saved=False)
  (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
