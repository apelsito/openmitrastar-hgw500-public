"""Verify input on the already-booted reset-v2 kernel; no kernel handoff or reset."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,re,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('reset',HERE.parent/'linux-7.3-ethernet-reset-v2/executor.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def main():
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--execute',action='store_true');p.add_argument('--baseline-boot',default='');p.add_argument('--lock');p.add_argument('--owner-pid',type=int);p.add_argument('--owner-ticks',type=int);p.add_argument('--lease-token')
 a=p.parse_args();config=json.loads(a.config.read_text());artifact=m.preflight(config)
 if not a.execute:print(json.dumps({'status':'PREFLIGHT_RUNNING_KERNEL_ONLY','artifact':artifact}));return
 prior=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/eth73-reset-loaded-cont-v4'
 r=json.loads((prior/'result.json').read_text());m.m.require(r['bootm']==1 and r['artifact']['sha256']==config['sha256'],'Boot receipt differs')
 a.output.mkdir(exist_ok=False);log=m.Log(a.output/'uart-redacted.txt');session=None
 result={'status':'STOP_RUNNING_KERNEL_ACCEPTANCE','bootm':0,'reboots':0,'flash_writes':0,'bootenv_writes':0,'artifact':artifact}
 try:
  backend=m.Backend(a);backend.force_lease();session=m.m.continuous_session(log,backend)
  nonce=hashlib.sha256(str(time.monotonic_ns()).encode()).hexdigest()[:32]
  flow=m.Flow(backend,session,nonce,config=config,output=a.output)
  flow.fresh();session.write(b'\n',timeout=3)
  boundary=bytearray();deadline=time.monotonic()+3
  while time.monotonic()<deadline:
   boundary+=session.read(4096,.05)
   if b'eth73>' in boundary:break
  session.write(('echo '+nonce+'\n').encode(),timeout=3)
  data=bytearray();deadline=time.monotonic()+15
  while time.monotonic()<deadline:
   session.check_safe();data+=session.read(4096,.05)
   if re.search(rb'(?m)^ETH73_NONCE='+nonce.encode()+rb'\r?$',data):break
  # Only bounded non-sensitive response bytes from this exact nonce command.
  text=data.decode('ascii','replace')
  result.update(response_bytes=len(data),nonce_seen=bool(re.search(rb'(?m)^ETH73_NONCE='+nonce.encode()+rb'\r?$',data)),prompt_seen=b'eth73>' in data)
  (a.output/'response-shape.json').write_text(json.dumps({'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'ascii_nonce_prompt_response':text if len(data)<1024 and not re.search(rb'(?i)(?:[0-9a-f]{2}:){5}|password|psk',data) else 'OMITTED'},indent=2)+'\n')
  m.m.require(result['nonce_seen'],'No fresh input response from booted PID1')
  result['status']='PASS_RUNNING_RESET_V2_UART_INPUT'
  result['kernel_status']=flow.command('status').decode(errors='replace')
  for command in ['modules','eth0state','eth1state','netdiag','netstats','interrupts','ethstats','eth1stats']:
   result[command]=flow.command(command).decode(errors='replace')
  import subprocess,socket
  ping=subprocess.run(['C:/Windows/System32/ping.exe','-n','3','-w','1000','192.168.1.91'],capture_output=True,timeout=8)
  result['ping']={'requests':3,'replies_ttl64':ping.stdout.count(b'TTL=64'),'exit_code':ping.returncode}
  flow.fresh();session.write(b'udpecho\n',timeout=3);flow.wait(rb'UDP_READY_PORT9009\r?\n',15)
  client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.bind(('192.168.1.49',0));client.settimeout(.4)
  echoed=0
  try:
   for i in range(20):
    payload=('ETH1-'+nonce+'-'+str(i)).encode();client.sendto(payload,('192.168.1.91',9009))
    try:
     data,peer=client.recvfrom(512);echoed+=int(data==payload and peer==('192.168.1.91',9009))
    except socket.timeout:pass
    time.sleep(.06)
  finally:client.close()
  accounting=flow.wait(m.PROMPT,20)
  result['udp']={'requests':20,'exact_echoes':echoed,'guest_accounting':accounting.decode(errors='replace')}
  result['netstats_after']=flow.command('netstats').decode(errors='replace')
  result['eth1stats_after']=flow.command('eth1stats').decode(errors='replace')
  result['status']='PASS_RESET_V2_ETH1_TRAFFIC' if echoed==20 and result['ping']['replies_ttl64']==3 else 'UART_PASS_ETH1_TRAFFIC_INCOMPLETE'
 except BaseException as error:
  result.update(error_type=type(error).__name__,error_reason=str(error));print(str(error),flush=True);raise
 finally:
  if session:session.close()
  (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
