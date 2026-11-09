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
 'runtime': 'uname -r; cat /proc/uptime; ps; cat /proc/net/tcp; cat /proc/sys/kernel/tainted',
 'faults': '/bin/busybox dmesg | tail -n 120',
 'radio': 'iw dev; iw reg get; cat /sys/class/net/wlan0/operstate; cat /proc/interrupts',
 'phy': 'iw phy phy0 info',
 'tls_self': 'ls -l /proc/$(pidof uhttpd)/fd 2>/dev/null; cat /proc/$(pidof uhttpd)/status 2>/dev/null',
}

class Flow(m.Flow):
 def shell_script(self,name):
  script=SCRIPTS[name];marker='RADIOETH73-END-'+self.nonce[:20]+'-'+name
  self.safe();self.fresh();self.s.write((script+"; printf '\\n"+marker+"\\n'\n").encode(),timeout=3)
  response=self.wait(rb'(?m)^'+marker.encode()+rb'\r?$',45)
  self.steps.append('shell:'+name);return parent.safe_text(response)
 def run(self):
  m.preflight(self.config);self.b.force_lease();self.fresh()
  # Prior exact-boot diagnostic owns this shell; interrupt only its foreground
  # blocked iw query, then require a fresh tagged shell/kernel response.
  self.s.write(b'\x03\n',timeout=3)
  time.sleep(.2)
  gates={}
  for name in ['runtime','faults']:
   gates[name]=self.shell_script(name)
   (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
  m.BASE.require(m.KERNEL.decode() in gates['runtime'],'Current shell kernel differs')
  # Keep radio query explicitly bounded; never block UART on an unbounded iw.
  SCRIPTS['radio']='/bin/busybox timeout -s KILL 5 iw dev; cat /sys/class/net/wlan0/operstate; cat /proc/interrupts'
  SCRIPTS['process_stacks']='ps; for p in /proc/33 /proc/40 /proc/41; do [ -d "$p" ] || continue; echo PROCESS_STATE; cat "$p/wchan" "$p/syscall"; done'
  for name in ['radio','process_stacks','tls_self']:
   gates[name]=self.shell_script(name)
   (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
  self.fresh();self.s.write(b'exit\n',timeout=3);self.wait(m.PROMPT,20)
  gates['after_status']=parent.safe_text(self.command('status'))
  (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
  return {'status':'PASS_RECOVERED_SHELL_AND_CURRENT_DIAGNOSTIC','gates':gates,'steps':self.steps,'bootm':0,'reboots':0,'flash_writes':0,'bootenv_writes':0}

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
