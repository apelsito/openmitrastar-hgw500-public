"""Diagnose current radioeth73 RAM instance through bounded UART shell commands."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE=HERE.parent/'linux-7.3-radioeth-ram-v1'
spec=importlib.util.spec_from_file_location('accept',HERE.parent/'linux-7.3-radioeth-accept-v4/executor.py');parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(parent)
m=parent.m
sys.path.insert(0,str(SOURCE))
from bounded_serial import BoundedSerialWriter

SCRIPTS={'runtime': 'uname -r; cat /proc/uptime; ps; cat /proc/sys/kernel/tainted', 'tls_events': 'for p in $(/bin/busybox pidof uhttpd); do echo TLS_PROCESS; cat /proc/$p/stat /proc/$p/wchan /proc/$p/syscall; /bin/busybox ls -l /proc/$p/fd; done', 'radio_auth': '/bin/busybox timeout -s KILL 4 /usr/sbin/hostapd_cli -p /run/hostapd all_sta; echo STATION_QUERY_RC=$?; /bin/busybox grep -c AP-STA-CONNECTED /run/hostapd-private.log; /bin/busybox grep -c AP-STA-DISCONNECTED /run/hostapd-private.log', 'fault_tail': '/bin/busybox dmesg -s 4096 | /bin/busybox tail -n 22', 'probe_begin': 'test ! -e /run/om73-signal-probe && : > /run/om73-signal-probe.b64; echo PROBE_INIT_RC=$?', 'probe_chunk_0': "printf '%s' 'f0VMRgEBAQAAAAAAAAAAAAIAXQABAAAAjAEBADQAAAC0BwAAAwQAADQAIAADACgACQAIAAEAAAAAAAAAAAABAAAAAQB8BQAAfAUAAAUAAAAAIAAAAQAAAHwFAAB8JQEAfCUBABgAAAAYAAAABgAAAAAgAABR5XRk' >> /run/om73-signal-probe.b64", 'probe_chunk_1': "printf '%s' 'AAAAAAAAAAAAAAAAAAAAAAAAAAAGAAAAEAAAAADaCHFYYQCIiugB2ADbSiQAAIogARBvIj8A4H5BavTx4cWhwQokAJAodRHyCdkA2gDbSiQAAIogQhBvIj8AiiAEEYlwi3FvIj8AqXAA2QDaANtKJAAAiiBBF28i' >> /run/om73-signal-probe.b64", 'probe_chunk_2': "printf '%s' 'PwAB8PHA4cbhxaPBC9oIdSh2i3AKIYAPAQBwBVIIAAAA2VUhwAAAIAIHTiHAARJoIWkBLgAQw7gyIIAPAQDsA/YaAoDfCRGCqXBeD8//AdiLcQvaANtKJAAAiiABEG8iPwCjwMHFwcbRwOB+ANtQc+AgxgfhxX1h' >> /run/om73-signal-probe.b64", 'probe_chunk_3': "printf '%s' '4HigjXxgYWugrFBzuffBxeB+4HgA21Bz4CDGB3xgIKxha/vx8cDhxuHFlSR+PRHYANkA2gDbSiQAAIogAxdvIj8ACiUAkBwAAwCpcQoggA8BAAAEOg/P/wLZANjyDs//LPSKIEEdbyI/AAokAJAL8olxCiCADwEA' >> /run/om73-signal-probe.b64", 'probe_chunk_4': "printf '%s' 'EAQWD8//A9nt8YogAhtvIj8AE9mKIEIQbyI/AAAWAHABAHwlCiGADwEAfCUKIoAPAQCMJYogQxdvIj8Af9nT8QDeANhAwItxqXAA2gDbSiQAAIogBBFvIj8ACiEAgBgAAwAKIIAPAQAgBK4Oz/8E2alwuvEAwQog' >> /run/om73-signal-probe.b64", 'probe_chunk_5': "printf '%s' 'gA8BACwEmg7P/wDAD3mK6QoggA8BAEAEJg7P/wDZp/H/4QryCiCADwEAUAQSDs//Admd8Ui4x7iL4BoBCQABLgBwAACQCOC4hfKA2gDZg8DWDs//CiCADwAAAkKpcQDag8NKJAAAiiBBHW8iPwAIcQoggA8BAGQE' >> /run/om73-signal-probe.b64", 'probe_chunk_6': "printf '%s' 'Jg7P/wPBCiCADwEAdAQaDs//BcEKIIAPAQB8BAoOz/8GwQoggA8BAIwE/g3P/6DaANlVJMA4eg7P/0HAoNhCwKlxCiCADwAABEIB2oHDSiQAAIogQR1vIj8ACHEIdgoggA8BAJwEwg3P/wLBCiCADwEArASyDc//' >> /run/om73-signal-probe.b64", 'probe_chunk_7': "printf '%s' 'qe5KFAE2CiCADwEAvASiDc//pBQBMAoggA8BAMAEkg3P/5AUATAKIIAPAQDMBIINz/+gFAEwCiCADwEA3ARyDc//SRQBNgoggA8BAOgEYg3P/woggA8BAPAE9gzP/wHZVPEH2KlxANoA20okAACKIEEdbyI/AAoh' >> /run/om73-signal-probe.b64", 'probe_chunk_8': "printf '%s' 'AIAK8goggA8BAAgFKg3P/wXZQPHBbojmJfUKIIAPAQAUBbYMz/8G2TTx4HgwMTIzNDU2Nzg5YWJjZGVmAAAAAENMT05FX0VSUk9SPQAAAABUUkFDRU1FX0VSUk9SPQAAV0FJVF9FUlJPUj0AVFJBQ0VfV0FJVF9T' >> /run/om73-signal-probe.b64", 'probe_chunk_9': "printf '%s' 'VEFUVVM9AABUUkFDRV9FWElURUQKAAAAVFJBQ0VfU0lHTkFMX0VYSVQKAABHRVRTSUdJTkZPX1JDPQAAU0lHTkFMPQBTSUdOQUxfQ09ERT0AAAAARkFVTFRfQUREUkVTUz0AAEdFVFJFR1NFVF9SQz0AAABSRUdT' >> /run/om73-signal-probe.b64", 'probe_chunk_10': "printf '%s' 'RVRfQllURVM9AAAAUEM9AFJFVFVSTl9QQz0AAEJSQU5DSF9UQVJHRVQ9AABTVEFUVVMzMj0AAABFRkE9AAAAAFRSQUNFX0ZBVUxUX0NBUFRVUkVECgAAAENPTlRfRVJST1I9AFRSQUNFX1NUT1BfTElNSVQKAAAA' >> /run/om73-signal-probe.b64", 'probe_chunk_11': "printf '%s' 'UEFUSD0vYmluOi91c3IvYmluOi91c3Ivc2JpbgAAAAAvdXNyL3NiaW4vZHJvcGJlYXJtdWx0aQBkcm9wYmVhcgAAAAAtVgAAMHgAAAAAAAAAAAoASAUBAGAFAQBsBQEAAAAAACgFAQAAAAAAR0NDOiAoQVJDb21w' >> /run/om73-signal-probe.b64", 'probe_chunk_12': "printf '%s' 'YWN0IEFSQzcwMCBMaW51eCB1Y2xpYmMgdG9vbGNoYWluIC0gYnVpbGQgMTA1MDQpIDE1LjIuMABBJQAAAEFSQwABHQAAAAQDBQIHYXJjNzAwAAkEDAEOARBCUwAUAQAAAAAAAAAAAAAAAAAAAAAAAAAAAACUAAEA' >> /run/om73-signal-probe.b64", 'probe_chunk_13': "printf '%s' 'AAAAAAMAAQAAAAAA7AMBAAAAAAADAAIAAAAAAHwlAQAAAAAAAwADAAAAAAAAAAAAAAAAAAMABAAAAAAAAAAAAAAAAAADAAUAAQAAAAAAAAAAAAAABADx/wkAAACUAAEAIAAAAAIAAQANAAAAtAABAEAAAAACAAEA' >> /run/om73-signal-probe.b64", 'probe_chunk_14': "printf '%s' 'FAAAAPQAAQBoAAAAAgABABgAAAB8JQEAEAAAAAEAAwAfAAAAjCUBAAgAAAABAAMAJQAAAFwBAQAeAAAAEgABADEAAACMAQEAXgIAABIAAQAsAAAAlCUBAAAAAAAQAAMAOAAAAHwBAQAQAAAAEgABAD8AAACUJQEA' >> /run/om73-signal-probe.b64", 'probe_chunk_15': "printf '%s' 'AAAAABAAAwBGAAAAlCUBAAAAAAAQAAMAAHByb2JlLmMAc2F5AGZpbmlzaABoZXgAYXJncy4xAGVudi4wAG1lbWNweQBfX2Jzc19zdGFydABtZW1zZXQAX2VkYXRhAF9lbmQAAC5zeW10YWIALnN0cnRhYgAuc2hz' >> /run/om73-signal-probe.b64", 'probe_chunk_16': "printf '%s' 'dHJ0YWIALnRleHQALnJvZGF0YQAuZGF0YQAuY29tbWVudAAuQVJDLmF0dHJpYnV0ZXMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAbAAAAAQAAAAYAAACUAAEAlAAAAFgDAAAAAAAA' >> /run/om73-signal-probe.b64", 'probe_chunk_17': "printf '%s' 'AAAAAAQAAAAAAAAAIQAAAAEAAAACAAAA7AMBAOwDAACQAQAAAAAAAAAAAAAEAAAAAAAAACkAAAABAAAAAwAAAHwlAQB8BQAAGAAAAAAAAAAAAAAABAAAAAAAAAAvAAAAAQAAADAAAAAAAAAAlAUAAEQAAAAAAAAA' >> /run/om73-signal-probe.b64", 'probe_chunk_18': "printf '%s' 'AAAAAAEAAAABAAAAOAAAAAEAAHAAAAAAAAAAANgFAAAmAAAAAAAAAAAAAAABAAAAAAAAAAEAAAACAAAAAAAAAAAAAAAABgAAIAEAAAcAAAAMAAAABAAAABAAAAAJAAAAAwAAAAAAAAAAAAAAIAcAAEsAAAAAAAAA' >> /run/om73-signal-probe.b64", 'probe_chunk_19': "printf '%s' 'AAAAAAEAAAAAAAAAEQAAAAMAAAAAAAAAAAAAAGsHAABIAAAAAAAAAAAAAAABAAAAAAAAAA==' >> /run/om73-signal-probe.b64", 'probe_decode': '/bin/busybox base64 -d /run/om73-signal-probe.b64 > /run/om73-signal-probe; /bin/busybox chmod 700 /run/om73-signal-probe; /bin/busybox sha256sum /run/om73-signal-probe; /bin/busybox rm /run/om73-signal-probe.b64', 'probe_run': '/bin/busybox timeout -s KILL 6 /run/om73-signal-probe; echo PROBE_RC=$?', 'upload_fixture': "printf '%s' 'IyEvYmluL3NoCmNhc2UgIiRDT05URU5UX0xFTkdUSCIgaW4gNjU1MzYpIDs7ICopIHByaW50ZiAiU3RhdHVzOiA0MTMgUGF5bG9hZCBUb28gTGFyZ2VcclxuQ29udGVudC1UeXBlOiB0ZXh0L3BsYWluXHJcblxyXG5yZWplY3RlZFxuIjsgZXhpdCAwOzsgZXNhYwpkaWdlc3Q9JCgvYmluL2J1c3lib3ggaGVhZCAtYyA2NTUzNiB8IC9iaW4vYnVzeWJveCBzaGEyNTZzdW0pCnByaW50ZiAiQ29udGVudC1UeXBlOiB0ZXh0L3BsYWluXHJcbkNhY2hlLUNvbnRyb2w6IG5vLXN0b3JlXHJcblxyXG4lc1xuIiAiJGRpZ2VzdCIK' | /bin/busybox base64 -d > /www/__traffic.cgi; /bin/busybox chmod 755 /www/__traffic.cgi; /bin/busybox sha256sum /www/__traffic.cgi", 'final_runtime': 'ps; cat /proc/uptime'}

class Flow(m.Flow):
 def shell_script(self,name):
  script=SCRIPTS[name];marker='RADIOETH73-END-'+self.nonce[:20]+'-'+name
  self.safe();self.fresh();self.s.write((script+"; printf '\\n"+marker+"\\n'\n").encode(),timeout=3)
  response=self.wait(rb'(?m)^'+marker.encode()+rb'\r?$',45)
  self.steps.append('shell:'+name);return parent.safe_text(response)
 def run(self):
  prior=json.loads((ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-physical-powercycle-v15/result.json').read_text())
  m.BASE.require(prior['artifact']['sha256']==self.config['sha256'] and prior['bootm']==1 and prior['flash_writes']==prior['bootenv_writes']==0,'Exact new RAM boot absent')
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
  return {'status':'PASS_EVENTS_RAM_DIAGNOSTIC_WITH_PROBE_AND_UPLOAD_FIXTURE','gates':gates,'steps':self.steps,'bootm':0,'reboots':0,'flash_writes':0,'bootenv_writes':0}

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
