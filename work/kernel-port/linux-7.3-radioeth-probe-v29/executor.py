"""Diagnose current radioeth73 RAM instance through bounded UART shell commands."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('accept',HERE.parent/'linux-7.3-radioeth-accept-v4/executor.py');parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
m=parent.m
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter

SCRIPTS={'runtime': 'uname -r', 'init': ': > /run/om73-probe.b64', 'p0': "printf %s 'f0VMRgEBAQAAAAAAAAAAAAIAXQABAAAAjAEBADQAAAD8BwAAAwQAADQAIAADACgA' >> /run/om73-probe.b64", 'p1': "printf %s 'CQAIAAEAAAAAAAAAAAABAAAAAQDEBQAAxAUAAAUAAAAAIAAAAQAAAMQFAADEJQEA' >> /run/om73-probe.b64", 'p2': "printf %s 'xCUBABgAAAAYAAAABgAAAAAgAABR5XRkAAAAAAAAAAAAAAAAAAAAAAAAAAAGAAAA' >> /run/om73-probe.b64", 'p3': "printf %s 'EAAAAADaCHFYYQCIiugB2ADbSiQAAIogARBvIj8A4H5BavTx4cWhwQokAJAodRHy' >> /run/om73-probe.b64", 'p4': "printf %s 'CdkA2gDbSiQAAIogQhBvIj8AiiAEEYlwi3FvIj8AqXAA2QDaANtKJAAAiiBBF28i' >> /run/om73-probe.b64", 'p5': "printf %s 'PwAB8PHA4cbhxaPBC9oIdSh2i3AKIYAPAQC4BVIIAAAA2VUhwAAAIAIHTiHAARJo' >> /run/om73-probe.b64", 'p6': "printf %s 'IWkBLgAQw7gyIIAPAQAcBPYaAoDfCRGCqXBeD8//AdiLcQvaANtKJAAAiiABEG8i' >> /run/om73-probe.b64", 'p7': "printf %s 'PwCjwMHFwcbRwOB+ANtQc+AgxgfhxX1h4HigjXxgYWugrFBzuffBxeB+4HgA21Bz' >> /run/om73-probe.b64", 'p8': "printf %s '4CDGB3xgIKxha/vx8cDhxuHFlSR+PRHYANkA2gDbSiQAAIogAxdvIj8ACiUAkBwA' >> /run/om73-probe.b64", 'p9': "printf %s 'AwCpcQoggA8BADAEOg/P/wLZANjyDs//LPSKIEEdbyI/AAokAJAL8olxCiCADwEA' >> /run/om73-probe.b64", 'p10': "printf %s 'QAQWD8//A9nt8YogAhtvIj8AE9mKIEIQbyI/AAAWAHABAMQlCiGADwEAxCUKIoAP' >> /run/om73-probe.b64", 'p11': "printf %s 'AQDUJYogQxdvIj8Af9nT8QDeANhAwItxqXAA2gDbSiQAAIogBBFvIj8ACiEAgBgA' >> /run/om73-probe.b64", 'p12': "printf %s 'AwAKIIAPAQBQBK4Oz/8E2alwuvEAwQoggA8BAFwEmg7P/wDEj3iK6AoggA8BAHAE' >> /run/om73-probe.b64", 'p13': "printf %s 'Jg7P/wDZp/H/4AryCiCADwEAgAQSDs//Admd8ZjuIdgB2wm4FLupcQDaSiQAAIog' >> /run/om73-probe.b64", 'p14': "printf %s 'QR1vIj8ACiEAgAryCiCADwEAlARCDs//B9nM8Ui8x7yL5BoBCQABLgxzAACQCOC8' >> /run/om73-probe.b64", 'p15': "printf %s 'hfKA2gDZg8CmDs//CiCADwAAAkKpcQDag8NKJAAAiiBBHW8iPwAIcQoggA8BAKwE' >> /run/om73-probe.b64", 'p16': "printf %s '9g3P/wPBCiCADwEAvATqDc//BcEKIIAPAQDEBNoNz/8GwQoggA8BANQEzg3P/6Da' >> /run/om73-probe.b64", 'p17': "printf %s 'ANlVJMA4Sg7P/0HAoNhCwKlxCiCADwAABEIB2oHDSiQAAIogQR1vIj8ACHEIdgog' >> /run/om73-probe.b64", 'p18': "printf %s 'gA8BAOQEkg3P/wLBCiCADwEA9ASCDc//qe5KFAE2CiCADwEABAVyDc//pBQBMAog' >> /run/om73-probe.b64", 'p19': "printf %s 'gA8BAAgFYg3P/5AUATAKIIAPAQAUBVINz/+gFAEwCiCADwEAJAVCDc//SRQBNgog' >> /run/om73-probe.b64", 'p20': "printf %s 'gA8BADAFMg3P/woggA8BADgFxgzP/wHZPPEH2KlxANoA20okAACKIEEdbyI/AAoh' >> /run/om73-probe.b64", 'p21': "printf %s 'AIAK8goggA8BAFAF+gzP/wXZKPHBbojmDfUKIIAPAQBcBYYMz/8G2Rzx4HgwMTIz' >> /run/om73-probe.b64", 'p22': "printf %s 'NDU2Nzg5YWJjZGVmAAAAAENMT05FX0VSUk9SPQAAAABUUkFDRU1FX0VSUk9SPQAA' >> /run/om73-probe.b64", 'p23': "printf %s 'V0FJVF9FUlJPUj0AVFJBQ0VfV0FJVF9TVEFUVVM9AABUUkFDRV9FWElURUQKAAAA' >> /run/om73-probe.b64", 'p24': "printf %s 'VFJBQ0VfU0lHTkFMX0VYSVQKAABFWElUS0lMTF9PUFRJT05fRVJST1I9AABHRVRT' >> /run/om73-probe.b64", 'p25': "printf %s 'SUdJTkZPX1JDPQAAU0lHTkFMPQBTSUdOQUxfQ09ERT0AAAAARkFVTFRfQUREUkVT' >> /run/om73-probe.b64", 'p26': "printf %s 'Uz0AAEdFVFJFR1NFVF9SQz0AAABSRUdTRVRfQllURVM9AAAAUEM9AFJFVFVSTl9Q' >> /run/om73-probe.b64", 'p27': "printf %s 'Qz0AAEJSQU5DSF9UQVJHRVQ9AABTVEFUVVMzMj0AAABFRkE9AAAAAFRSQUNFX0ZB' >> /run/om73-probe.b64", 'p28': "printf %s 'VUxUX0NBUFRVUkVECgAAAENPTlRfRVJST1I9AFRSQUNFX1NUT1BfTElNSVQKAAAA' >> /run/om73-probe.b64", 'p29': "printf %s 'UEFUSD0vYmluOi91c3IvYmluOi91c3Ivc2JpbgAAAAAvdXNyL3NiaW4vZHJvcGJl' >> /run/om73-probe.b64", 'p30': "printf %s 'YXJtdWx0aQBkcm9wYmVhcgAAAAAtVgAAMHgAAAAAAAAAAAoAkAUBAKgFAQC0BQEA' >> /run/om73-probe.b64", 'p31': "printf %s 'AAAAAHAFAQAAAAAAR0NDOiAoQVJDb21wYWN0IEFSQzcwMCBMaW51eCB1Y2xpYmMg' >> /run/om73-probe.b64", 'p32': "printf %s 'dG9vbGNoYWluIC0gYnVpbGQgMTA1MDQpIDE1LjIuMABBJQAAAEFSQwABHQAAAAQD' >> /run/om73-probe.b64", 'p33': "printf %s 'BQIHYXJjNzAwAAkEDAEOARBCUwAUAQAAAAAAAAAAAAAAAAAAAAAAAAAAAACUAAEA' >> /run/om73-probe.b64", 'p34': "printf %s 'AAAAAAMAAQAAAAAAHAQBAAAAAAADAAIAAAAAAMQlAQAAAAAAAwADAAAAAAAAAAAA' >> /run/om73-probe.b64", 'p35': "printf %s 'AAAAAAMABAAAAAAAAAAAAAAAAAADAAUAAQAAAAAAAAAAAAAABADx/wkAAACUAAEA' >> /run/om73-probe.b64", 'p36': "printf %s 'IAAAAAIAAQANAAAAtAABAEAAAAACAAEAFAAAAPQAAQBoAAAAAgABABgAAADEJQEA' >> /run/om73-probe.b64", 'p37': "printf %s 'EAAAAAEAAwAfAAAA1CUBAAgAAAABAAMAJQAAAFwBAQAeAAAAEgABADEAAACMAQEA' >> /run/om73-probe.b64", 'p38': "printf %s 'jgIAABIAAQAsAAAA3CUBAAAAAAAQAAMAOAAAAHwBAQAQAAAAEgABAD8AAADcJQEA' >> /run/om73-probe.b64", 'p39': "printf %s 'AAAAABAAAwBGAAAA3CUBAAAAAAAQAAMAAHByb2JlLmMAc2F5AGZpbmlzaABoZXgA' >> /run/om73-probe.b64", 'p40': "printf %s 'YXJncy4xAGVudi4wAG1lbWNweQBfX2Jzc19zdGFydABtZW1zZXQAX2VkYXRhAF9l' >> /run/om73-probe.b64", 'p41': "printf %s 'bmQAAC5zeW10YWIALnN0cnRhYgAuc2hzdHJ0YWIALnRleHQALnJvZGF0YQAuZGF0' >> /run/om73-probe.b64", 'p42': "printf %s 'YQAuY29tbWVudAAuQVJDLmF0dHJpYnV0ZXMAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' >> /run/om73-probe.b64", 'p43': "printf %s 'AAAAAAAAAAAAAAAAAAAAAAAAAAAbAAAAAQAAAAYAAACUAAEAlAAAAIgDAAAAAAAA' >> /run/om73-probe.b64", 'p44': "printf %s 'AAAAAAQAAAAAAAAAIQAAAAEAAAACAAAAHAQBABwEAACoAQAAAAAAAAAAAAAEAAAA' >> /run/om73-probe.b64", 'p45': "printf %s 'AAAAACkAAAABAAAAAwAAAMQlAQDEBQAAGAAAAAAAAAAAAAAABAAAAAAAAAAvAAAA' >> /run/om73-probe.b64", 'p46': "printf %s 'AQAAADAAAAAAAAAA3AUAAEQAAAAAAAAAAAAAAAEAAAABAAAAOAAAAAEAAHAAAAAA' >> /run/om73-probe.b64", 'p47': "printf %s 'AAAAACAGAAAmAAAAAAAAAAAAAAABAAAAAAAAAAEAAAACAAAAAAAAAAAAAABIBgAA' >> /run/om73-probe.b64", 'p48': "printf %s 'IAEAAAcAAAAMAAAABAAAABAAAAAJAAAAAwAAAAAAAAAAAAAAaAcAAEsAAAAAAAAA' >> /run/om73-probe.b64", 'p49': "printf %s 'AAAAAAEAAAAAAAAAEQAAAAMAAAAAAAAAAAAAALMHAABIAAAAAAAAAAAAAAABAAAA' >> /run/om73-probe.b64", 'p50': "printf %s 'AAAAAA==' >> /run/om73-probe.b64", 'decode': ' /bin/busybox base64 -d /run/om73-probe.b64 > /run/om73-signal-probe; chmod 700 /run/om73-signal-probe; sha256sum /run/om73-signal-probe', 'signal': ' /bin/busybox timeout -s KILL 6 /run/om73-signal-probe; echo PROBE_RC=$?', 'after': 'cat /proc/uptime; ps'}

class Flow(m.Flow):
 def shell_script(self,name):
  script=SCRIPTS[name];marker='R29-'+self.nonce[:8]+'-'+name
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
   if name=='decode':m.BASE.require('b256b414779f1f3e7af678b8b8428b6806bb2675a8bcbad9638de4a99284b4d8' in gates[name],'Probe hash mismatch; do not execute')
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
