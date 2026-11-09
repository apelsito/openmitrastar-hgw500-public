"""Diagnose current radioeth73 RAM instance through bounded UART shell commands."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('accept',HERE.parent/'linux-7.3-radioeth-accept-v4/executor.py');parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
m=parent.m
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter

SCRIPTS={
 'shellnonce': "printf 'SHELL_READY\\n'; uname -r",
 'pause_tls': 'kill -STOP 33; echo TLS_STOP_RC=$?; cat /proc/33/stat',
 'processes': 'ps',
 'fault_summary': '/bin/busybox dmesg -s 8192 | /bin/busybox grep -E "unalign|SIGBUS|dropbear|uhttpd|fault|error|trap|signal" | /bin/busybox tail -n 12',
 'kernel_faults': '/bin/busybox dmesg -s 4096 | /bin/busybox tail -n 12',
 'radio_bounded': '/bin/busybox timeout -s KILL 3 /usr/sbin/iw dev; echo IW_RC=$?',
 'process_state': 'cat /proc/33/wchan /proc/33/syscall; echo TLS_STATE_END',
}


class Flow(m.Flow):
 def shell_script(self,name):
  script=SCRIPTS[name];marker='RADIOETH73-END-'+self.nonce[:20]+'-'+name
  self.safe();self.fresh();self.s.write((script+"; printf '\\n"+marker+"\\n'\n").encode(),timeout=3)
  response=self.wait(rb'(?m)^'+marker.encode()+rb'\r?$',45)
  self.steps.append('shell:'+name);return parent.safe_text(response)
 def run(self):
  m.preflight(self.config);self.b.force_lease();self.fresh();self.s.write(b'\x03\n',timeout=3)
  time.sleep(.3)
  gates={}
  for name in SCRIPTS:
   gates[name]=self.shell_script(name)
   (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
  m.BASE.require(m.KERNEL.decode() in gates['shellnonce'],'Kernel identity differs')
  self.fresh();self.s.write(b'exit\n',timeout=3);self.wait(m.PROMPT,20)
  gates['after_status']=parent.safe_text(self.command('status'))
  (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
  return {'status':'PASS_SHORT_DIAG_TLS_PAUSED','gates':gates,'steps':self.steps,'bootm':0,'reboots':0,'flash_writes':0,'bootenv_writes':0}

def main():
 p=argparse.ArgumentParser()
 for name in ['config','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--execute',action='store_true');p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token');p.add_argument('--baseline-boot',default='')
 a=p.parse_args();config=json.loads(a.config.read_text());artifact=m.preflight(config)
 if not a.execute:print(json.dumps({'status':'PASS_CURRENT_RAM_READONLY_PREFLIGHT','artifact':artifact}));return
 a.output.mkdir(exist_ok=False);log=m.Log(a.output/'uart-redacted.txt');session=flow=None
 result={'status':'STOP_CURRENT_RAM_DIAGNOSTIC','artifact':artifact,'bootm':0,'reboots':0,'flash_writes':0,'bootenv_writes':0}
 try:
  backend=m.m.Backend(a);backend.force_lease();session=m.BASE.continuous_session(log,backend);writer=BoundedSerialWriter(session);session.write=writer.write
  flow=Flow(backend,session,hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32],config=config,output=a.output);result.update(flow.run())
 except BaseException as error:
  result.update(error_type=type(error).__name__,error_reason=str(error),steps=flow.steps if flow else []);print('RADIOETH73_STOP '+str(error),flush=True);raise
 finally:
  if session:session.close()
  result.update(raw_uart_saved=False);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
