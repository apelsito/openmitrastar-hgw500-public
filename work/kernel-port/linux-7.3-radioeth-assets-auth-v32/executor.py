"""Diagnose current radioeth73 RAM instance through bounded UART shell commands."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('accept',HERE.parent/'linux-7.3-radioeth-accept-v4/executor.py');parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
m=parent.m
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter

SCRIPTS={'runtime': 'uname -r', 'old_pin': 'sha256sum /www/__assets.cgi', 'auth_method': "sed -i 's@auth=$(/bin/sh@auth=$(REQUEST_METHOD=GET /bin/sh@' /www/__assets.cgi", 'permission': 'chmod 755 /www/__assets.cgi; sha256sum /www/__assets.cgi', 'after': 'cat /proc/uptime'}

class Flow(m.Flow):
 def shell_script(self,name):
  script=SCRIPTS[name];marker='R32-'+self.nonce[:8]+'-'+name
  self.safe();self.fresh()
  payload=(script+"; printf '\\n"+marker+"\\n'\n").encode()
  for offset in range(0,len(payload),8):
   self.safe();self.s.write(payload[offset:offset+8],timeout=3);time.sleep(.02)
  response=self.wait(rb'(?m)^'+marker.encode()+rb'\r?$',45)
  self.steps.append('shell:'+name);return parent.safe_text(response)
 def run(self):
  status=self.synchronize_nonce(m.KERNEL);gates={'kernel':parent.safe_text(status)}
  for name in ['eth1txdiag','eth1stats','netstats','interrupts']:
   gates[name]=parent.safe_text(self.command(name));(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
  self.fresh();self.s.write(b'shell\n',timeout=3)
  # Newlines and tagged output synchronize shell regardless of prompt shape.
  time.sleep(.2)
  for name in SCRIPTS:
   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
   if name=='old_pin':m.BASE.require('b1de8751f91aadb92c8bd590c5d59471fcd5f5ae6445b6ec20385b6ce984d3e8' in gates[name],'CGI parent drift')
   if name=='permission':m.BASE.require('7ff57b2cebe3f75c18daef7d259e80d5f2c3315b31551173897a9bd26ab376f0' in gates[name],'CGI auth patch drift')
  self.fresh();self.s.write(b'exit\n',timeout=3);self.wait(m.PROMPT,20)
  gates['after_status']=parent.safe_text(self.command('status'))
  (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
  return {'status':'PASS_REDACTED_STATION_OBSERVATION','gates':gates,'steps':self.steps,'bootm':0,'reboots':0,'flash_writes':0,'bootenv_writes':0}

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
