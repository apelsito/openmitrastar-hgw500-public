"""Diagnose current radioeth73 RAM instance through bounded UART shell commands."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('accept',HERE.parent/'linux-7.3-radioeth-accept-v4/executor.py');parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
m=parent.m
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter

SCRIPTS={'runtime': 'uname -r', 'cfg_init': ': > /run/om73-web.conf', 'c0': "printf '%s\\n' '*/api/v1/status:/bin/sh' >> /run/om73-web.conf", 'c1': "printf '%s\\n' '*/api/v1/capabilities:/bin/sh' >> /run/om73-web.conf", 'c2': "printf '%s\\n' '*/api/v1/storage:/bin/sh' >> /run/om73-web.conf", 'c3': "printf '%s\\n' '*/api/v1/network:/bin/sh' >> /run/om73-web.conf", 'c4': "printf '%s\\n' '*/api/v1/firmware:/bin/sh' >> /run/om73-web.conf", 'c5': "printf '%s\\n' '*/api/v1/session:/bin/sh' >> /run/om73-web.conf", 'c6': "printf '%s\\n' '*/api/v1/hardware-led-test:/bin/sh' >> /run/om73-web.conf", 'c7': "printf '%s\\n' '*/api/v1/frontend:/bin/sh' >> /run/om73-web.conf", 'c8': "printf '%s\\n' '*/api/v1/ssh:/bin/sh' >> /run/om73-web.conf", 'c9': "printf '%s\\n' '*/api/v1/clients:/bin/sh' >> /run/om73-web.conf", 'c10': "printf '%s\\n' '*/api/v1/privacy:/bin/sh' >> /run/om73-web.conf", 'c11': "printf '%s\\n' '*/api/v1/packages:/bin/sh' >> /run/om73-web.conf", 'c12': "printf '%s\\n' '*/api/v1/hardware:/bin/sh' >> /run/om73-web.conf", 'c13': "printf '%s\\n' '*/api/v1/diagnostics:/bin/sh' >> /run/om73-web.conf", 'args_init': ': > /run/om73-webargs', 'a0': "printf %s '/usr/sbin/uhttpd -f -c /run/om73-web.conf -s 0.0.0.0:443 -h /www -C /etc/lyoko/t' >> /run/om73-webargs", 'a1': "printf %s 'ls/server.pem -K /etc/lyoko/tls/server.key -D -S -I index.cgi -x /api/v1 -i .cgi' >> /run/om73-webargs", 'a2': "printf %s '=/bin/sh -n 2 -N 8 -t 15 -T 20' >> /run/om73-webargs", 'launch': 'p=$(/bin/busybox pidof uhttpd); test -n "$p" && kill -TERM $p; sleep 1; /bin/busybox sh -c "$(cat /run/om73-webargs)" >/run/uhttpd-api.log 2>&1 & echo HTTPS_API_PID=$!; sleep 1; /bin/busybox pidof uhttpd', 'after': 'cat /proc/uptime; cat /run/uhttpd-api.log'}

class Flow(m.Flow):
 def shell_script(self,name):
  script=SCRIPTS[name];marker='R27-'+self.nonce[:8]+'-'+name
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
