"""Accept the same already-booted radioeth73 RAM kernel; no handoff/reboot."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('radioeth_v1',SOURCE/'executor.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter

def safe_text(data):
 lines=[]
 for line in data.decode('ascii','replace').splitlines():
  if re.search(r'(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|password|psk|calibration|private.key|ssid|token_enc',line):continue
  lines.append(line)
 return '\n'.join(lines)

class Flow(m.Flow):
 def command(self,command,prompt=m.PROMPT,seconds=30):
  if command in {"radioes","wlanup","radioap","apstatus"}:
   self.safe();self.b.force_lease();self.fresh();self.s.write(command.encode()+b"\n",timeout=3)
   response=self.wait(prompt,seconds);self.steps.append(command);return response
  return super().command(command,prompt,seconds)

 def run(self):
  status=self.synchronize_nonce(m.KERNEL);gates={'kernel':safe_text(status)}
  for name in ['eth1down','eth0up','eth0state','eth0txdiag','ethstats','netstats','status']:
   gates[name]=safe_text(self.command(name,seconds=45))
   (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\n')
  return {'status':'PASS_ETH0_ACTIVATED_CURRENT_RAM','bootm':0,'reboots':0,'flash_writes':0,'bootenv_writes':0,'gates':gates,'steps':self.steps}

def main():
 p=argparse.ArgumentParser()
 for name in ['config','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--execute',action='store_true');p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token');p.add_argument('--baseline-boot',default='')
 a=p.parse_args();config=json.loads(a.config.read_text());artifact=m.preflight(config)
 if not a.execute:print(json.dumps({'status':'PASS_SAME_RAM_KERNEL_ATTACH_PREFLIGHT','artifact':artifact}));return
 a.output.mkdir(exist_ok=False);log=m.Log(a.output/'uart-redacted.txt');session=flow=None
 result={'status':'STOP_SAME_RAM_KERNEL_ACCEPTANCE','artifact':artifact,'flash_writes':0,'bootenv_writes':0,'reboots':0,'bootm':0}
 try:
  backend=m.m.Backend(a);backend.force_lease();session=m.BASE.continuous_session(log,backend)
  writer=BoundedSerialWriter(session);session.write=writer.write
  flow=Flow(backend,session,hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32],config=config,output=a.output)
  result.update(flow.run())
 except BaseException as error:
  result.update(error_type=type(error).__name__,error_reason=str(error),steps=flow.steps if flow else []);print('RADIOETH73_STOP '+str(error),flush=True);raise
 finally:
  if session:session.close()
  result.update(redacted_lines=log.lines,omitted_lines=log.omitted,raw_uart_saved=False)
  (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
