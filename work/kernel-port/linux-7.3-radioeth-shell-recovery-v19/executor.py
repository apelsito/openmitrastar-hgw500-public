"""Diagnose current radioeth73 RAM instance through bounded UART shell commands."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('accept',HERE.parent/'linux-7.3-radioeth-accept-v4/executor.py');parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
m=parent.m
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter

SCRIPTS={'runtime': 'uname -r', 'quiet': 'echo 3 > /proc/sys/kernel/printk; /bin/busybox stty -echo; echo QUIET_RC=$?', 'auth': '/bin/busybox ln -sf busybox /bin/id; ls -ln /run/openmitrastar/secrets/web.password.sha256; id -u', 'fixture_prep': ': > /run/om73-upload.b64', 'f0': "printf %s 'IyEvYmluL3NoCmNhc2UgIiRDT05URU5UX0xFTkdUSCIgaW4g' >> /run/om73-upload.b64", 'f1': "printf %s 'NjU1MzYpIDs7ICopIHByaW50ZiAiU3RhdHVzOiA0MTMgUGF5' >> /run/om73-upload.b64", 'f2': "printf %s 'bG9hZCBUb28gTGFyZ2VcclxuQ29udGVudC1UeXBlOiB0ZXh0' >> /run/om73-upload.b64", 'f3': "printf %s 'L3BsYWluXHJcblxyXG5yZWplY3RlZFxuIjsgZXhpdCAwOzsg' >> /run/om73-upload.b64", 'f4': "printf %s 'ZXNhYwpkaWdlc3Q9JCgvYmluL2J1c3lib3ggaGVhZCAtYyA2' >> /run/om73-upload.b64", 'f5': "printf %s 'NTUzNiB8IC9iaW4vYnVzeWJveCBzaGEyNTZzdW0pCnByaW50' >> /run/om73-upload.b64", 'f6': "printf %s 'ZiAiQ29udGVudC1UeXBlOiB0ZXh0L3BsYWluXHJcbkNhY2hl' >> /run/om73-upload.b64", 'f7': "printf %s 'LUNvbnRyb2w6IG5vLXN0b3JlXHJcblxyXG4lc1xuIiAiJGRp' >> /run/om73-upload.b64", 'f8': "printf %s 'Z2VzdCIK' >> /run/om73-upload.b64", 'fixture_decode': ' /bin/busybox base64 -d /run/om73-upload.b64 > /www/__traffic.cgi; chmod 755 /www/__traffic.cgi; sha256sum /www/__traffic.cgi', 'after': 'cat /proc/uptime'}

class Flow(m.Flow):
 def shell_script(self,name):
  script=SCRIPTS[name];marker='R19-'+self.nonce[:8]+'-'+name
  self.safe();self.fresh()
  payload=(script+"; printf '\\n"+marker+"\\n'\n").encode()
  for offset in range(0,len(payload),8):
   self.safe();self.s.write(payload[offset:offset+8],timeout=3);time.sleep(.02)
  response=self.wait(rb'(?m)^'+marker.encode()+rb'\r?$',45)
  self.steps.append('shell:'+name);return parent.safe_text(response)
 def run(self):
  m.preflight(self.config);self.b.force_lease();self.fresh()
  # Prior exact-boot diagnostic owns this shell; interrupt only its foreground
  # blocked iw query, then require a fresh tagged shell/kernel response.
  self.s.write(b'\x03\x15\n',timeout=3)
  time.sleep(.2)
  gates={}
  for name in SCRIPTS:
   gates[name]=self.shell_script(name)
   (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
   if name=='runtime':m.BASE.require(m.KERNEL.decode() in gates[name],'Current kernel differs')
   if name=='fixture_decode':m.BASE.require('3fe089928e1d2e90a3d8eddcebff12f24b81faeb1875dcd2841a4f0fe31fb3ae' in gates[name],'Upload fixture digest drift')
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
