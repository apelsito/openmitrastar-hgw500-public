"""Reboot the nonce-bound current RAM diagnostic and load event-syscall image.

One authorized RAM reboot; no flash or environment writes. Fresh guard, receiver/prompt proof,
explicit overlapped write deadlines, full CRC then exactly one kernel handoff.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('radioeth_v1',SOURCE/'executor.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter

class Flow(m.Flow):
 def run(self):
  m.preflight(self.config);self.b.force_lease();self.fresh()
  # Current console must prove a fresh nonce and exact running kernel before
  # the one authorized reset. The continuous receiver catches its Bootbase.
  (self.output/'READY_POWER_CYCLE.json').write_text(json.dumps({'status':'READY_NONCE_BOUND_RAM_REBOOT','artifact_sha256':self.config['sha256'],'flash_writes':0,'bootenv_writes':0,'prior_bootm':0})+'\n')
  print('RADIOETH73_V11_READY_CONTROLLED_RAM_REBOOT',flush=True)
  self.synchronize_nonce(m.KERNEL)
  self.safe();self.b.force_lease();self.fresh()
  self.s.write(b'reboot\n',timeout=3);self.steps.append('reboot-current-ram')
  deadline=self.clock()+90
  while self.clock()<deadline:
   try:self.catch_topaz_fast();break
   except TimeoutError:continue
  else:raise TimeoutError('Controlled RAM reboot did not return to Bootbase')
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
  self.wait(m.BASE.PROMPT,60);self.verify_ram();m.preflight(self.config)
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
  m.BASE.require(b'ETHLOAD=0' in self.command('ethload',seconds=45),'Ethernet load failed')
  results={'kernel_status':status.decode(errors='replace'),'userland':userland.decode(errors='replace')}
  for name in ['pcistatus','modules','eth0state','eth1state','eth1up','eth1txdiag','eth1stats','eth1state']:
   results[name]=self.command(name,seconds=45).decode(errors='replace')
  radio=self.command('radioload',seconds=120)
  results['radio_load']={'complete':b'RADIOLOAD_MODULES_COMPLETE' in radio,'successes':len(re.findall(rb'RADIO_MODULE_RESULT=0\r?\n',radio)),'sha256':hashlib.sha256(radio).hexdigest()}
  results['pci_after_radio']=self.command('pcistatus',seconds=45).decode(errors='replace')
  results['https_start']=self.command('httpsstart',seconds=45).decode(errors='replace')
  (self.output/'gates.json').write_text(json.dumps(results,indent=2)+'\n')
  return {'status':'PASS_RADIOETH73_RAM_BOOT_USERLAND_DRIVER_PROBE' if results['radio_load']['complete'] else 'RAM_BOOT_USERLAND_PASS_RADIO_INCOMPLETE','bootm':self.boots,'reboots':1,'flash_writes':0,'bootenv_writes':0,'steps':self.steps,'gates':results,'ethernet_https_traffic':'UNRUN','wifi_client':'UNRUN','persistent':'UNRUN'}

def main():
 p=argparse.ArgumentParser()
 for name in ['config','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--execute',action='store_true');p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token');p.add_argument('--baseline-boot',default='')
 a=p.parse_args();config=json.loads(a.config.read_text());artifact=m.preflight(config)
 if not a.execute:print(json.dumps({'status':'PASS_SAME_IMAGE_RAM_RECOVERY_PREFLIGHT','artifact':artifact}));return
 a.output.mkdir(exist_ok=False);log=m.Log(a.output/'uart-redacted.txt');session=flow=None
 result={'status':'STOP_RAM_TRANSFER_RECOVERY','artifact':artifact,'flash_writes':0,'bootenv_writes':0,'reboots':0}
 try:
  backend=m.m.Backend(a);backend.force_lease();session=m.BASE.continuous_session(log,backend)
  writer=BoundedSerialWriter(session);session.write=writer.write
  flow=Flow(backend,session,hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32],config=config,output=a.output)
  result.update(flow.run())
 except BaseException as error:
  result.update(error_type=type(error).__name__,error_reason=str(error),steps=flow.steps if flow else [],bootm=flow.boots if flow else 0,reboots=int(bool(flow and 'reboot-current-ram' in flow.steps)));print('RADIOETH73_STOP '+str(error),flush=True);raise
 finally:
  if session:session.close()
  result.update(redacted_lines=log.lines,omitted_lines=log.omitted,raw_uart_saved=False)
  (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
