"""Root-owned F367 client dispatch using the existing private WLAN harness.

Called only after exact F367 install and live CAC readiness in the same lease.
Import performs no network or hardware operation. The principal router is never
configured. Only a scoped temporary controller TCP rule/server may be created.
"""
from pathlib import Path
import base64,copy,ipaddress,json,re,secrets,subprocess,sys,time
import f367_aelita_harness as harness
import aelita_ssh_policy as policy
import run_aelita_2g_wpa2_runtime_psk_once as wpa
import f346_powershell as ps5

ROOT=Path(__file__).resolve().parents[1]

class ClientError(RuntimeError):pass
def require(value,why):
 if not value:raise ClientError(why)
def literal(value):return "'"+str(value).replace("'","''")+"'"

class Dispatcher:
 def __init__(self,host,plan,out,ready):
  self.host=host;self.plan=plan;self.out=out;self.ready=ready;self.config=copy.deepcopy(plan['aelita_config']);self.run_id=secrets.token_hex(16)
  self.config.update(run_id=self.run_id,image_bound=True,execution_allowed=True,image=plan['images']['f367'])
  self.launch='C:/ProgramData/OpenMitraStar/f367-launch/'+self.run_id;self.stage='C:/ProgramData/OpenMitraStar/f367-aelita/'+self.run_id
  self.rule='OpenMitraStar-F367-'+self.run_id;self.server=None;self.firewall_created=False;self.capture_attempted=False
  self.deadline=time.monotonic()+300
 def connect(self):
  require(self.host.guard(),'client_hardware_lease')
  client=self.config['client']
  return policy.connect_paramiko(host=client['control_ipv4'],user=client['user'],key_path=ROOT/client['key'],known_hosts=ROOT/client['known_hosts'],mode='pinned',connect_timeout=8)
 def ps(self,script,data='',timeout=60,cleanup=False):
  if not cleanup:
   remaining=self.deadline-time.monotonic();require(remaining>0,'aelita_client_deadline');timeout=min(timeout,max(1,int(remaining)))
  client=self.connect()
  try:
   stdin,stdout,stderr=client.exec_command(wpa.powershell_encoded(script),timeout=timeout)
   if data:stdin.write(data);stdin.flush()
   stdin.channel.shutdown_write();out=stdout.read();err=stderr.read();code=stdout.channel.recv_exit_status()
   require(len(out)<65536 and len(err)<65536,'aelita_output_limit')
   require(code==0,'aelita_powershell_failed')
   return out.decode('utf-8').lstrip('\ufeff')
  finally:client.close()
 def remote_json(self,name):
  require(name in ('capture.json','client.json','restore.json'),'client_result_name')
  return json.loads(self.ps('Get-Content -LiteralPath '+literal(self.stage+'/'+name)+' -Raw'))
 def stage_payload(self):
  files={'config.json':(json.dumps(self.config,indent=2)+'\n').encode(),
         'f367_aelita_client.ps1':(ROOT/'tools/f367_aelita_client_r2.ps1').read_bytes(),
         'reused-wlan-functions.ps1':harness.reused_functions().encode()}
  payload={name:base64.b64encode(data).decode() for name,data in files.items()}
  script="$ErrorActionPreference='Stop';$p="+literal(self.launch)+";for($d=[IO.DirectoryInfo]$p;$null -ne $d;$d=$d.Parent){if($d.Exists -and ($d.Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'stage-reparse'}};if(Test-Path -LiteralPath $p){throw 'stage-exists'};[void](New-Item -ItemType Directory -Path $p);& icacls.exe $p '/inheritance:r' '/grant:r' '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' 1>$null 2>$null;if($LASTEXITCODE -ne 0){throw 'acl'};$data=[Console]::In.ReadToEnd()|ConvertFrom-Json;foreach($name in @('config.json','f367_aelita_client.ps1','reused-wlan-functions.ps1')){[IO.File]::WriteAllBytes((Join-Path $p $name),[Convert]::FromBase64String($data.$name))};'STAGED'"
  require(self.ps(script,json.dumps(payload)).strip()=='STAGED','aelita_stage_failed')
  checks=';'.join("if((Get-FileHash -LiteralPath "+literal(self.launch+'/'+name)+").Hash.ToLowerInvariant() -cne "+literal(__import__('hashlib').sha256(data).hexdigest())+"){throw 'stage-hash'}" for name,data in files.items())
  self.ps(checks+";'HASHES_OK'")
 def action(self,name):
  require(name in ('Capture','Connect','Traffic','Restore'),'client_action')
  base=self.launch if name=='Capture' else self.stage
  script="& "+literal(base+'/f367_aelita_client.ps1')+' -Execute -Action '+name+' -ConfigPath '+literal(base+'/config.json')
  row=json.loads(self.ps(script,timeout=140 if name=='Traffic' else 85,cleanup=name=='Restore').strip())
  require(row.get('status')=='PASS' and row.get('run_id')==self.run_id,'client_phase_failed_'+name)
  return row
 def bind_private(self,target):
  radio=json.loads(self.host.ssh('/usr/sbin/om-radioctl status 5g').decode('ascii'))
  ssid=radio.get('ssid');require(isinstance(ssid,str) and 1<=len(ssid.encode())<=32,'client_ssid')
  secret=self.host.ssh('cat /run/openmitrastar/secrets/wpa2.psk',timeout=15).decode('ascii').strip()
  require(8<=len(secret)<=63 or bool(re.fullmatch('[0-9a-fA-F]{64}',secret)),'client_private_psk')
  data=json.dumps(dict(run_id=self.run_id,test_ssid=ssid,psk=secret,target_bssid_tag=target));secret=None
  script="Add-Type -AssemblyName System.Security;$b=[Text.Encoding]::UTF8.GetBytes([Console]::In.ReadToEnd());try{$d=[Security.Cryptography.ProtectedData]::Protect($b,$null,[Security.Cryptography.DataProtectionScope]::LocalMachine);[IO.File]::WriteAllBytes("+literal(self.stage+'/inputs.dpapi')+",$d)}finally{[Array]::Clear($b,0,$b.Length)};'PRIVATE_STAGED'"
  require(self.ps(script,data).strip()=='PRIVATE_STAGED','client_private_staging');data=None
 def snapshot(self):
  version=self.config['image']['version'];require(re.fullmatch('[A-Za-z0-9_.-]+',version),'client_version')
  raw=self.host.ssh('sh -s -- '+self.run_id+' '+version,(ROOT/'tools/f367_aelita_router_snapshot.sh').read_bytes(),timeout=20)
  return harness.parse_router_snapshot(raw.decode('ascii'))
 def firewall(self,client_ip,create):
  require(ipaddress.ip_address(client_ip) in ipaddress.ip_network('192.168.1.0/24') and client_ip not in ('192.168.1.1','192.168.1.49','192.168.1.63','192.168.1.90'),'client_firewall_address')
  if create:
   command="$ErrorActionPreference='Stop';if(Get-NetFirewallRule -Name "+literal(self.rule)+" -ErrorAction SilentlyContinue){throw 'existing-rule'};New-NetFirewallRule -Name "+literal(self.rule)+" -DisplayName "+literal(self.rule)+" -Group "+literal(self.rule)+" -Direction Inbound -Action Allow -Enabled True -Protocol TCP -LocalAddress 192.168.1.49 -LocalPort 8081 -RemoteAddress "+client_ip+" -Program "+literal(self.plan['network']['python_executable'])+" -Profile Any|Out-Null"
  else:
   command="$ErrorActionPreference='Stop';$r=Get-NetFirewallRule -Name "+literal(self.rule)+" -ErrorAction SilentlyContinue;if($r){if($r.Group -cne "+literal(self.rule)+"){throw 'foreign-rule'};$r|Remove-NetFirewallRule}; if(Get-NetFirewallRule -Name "+literal(self.rule)+" -ErrorAction SilentlyContinue){throw 'rule-remains'}"
  result=subprocess.run([ps5.executable(),'-NoProfile','-NonInteractive','-Command',command],env=ps5.environment(),capture_output=True,timeout=30)
  require(result.returncode==0,'client_firewall_create_failed' if create else 'client_firewall_cleanup_failed')
 def start_server(self,ip):
  self.firewall_created=True;self.firewall(ip,True)
  stdout=(self.out/'server.stdout').open('wb');stderr=(self.out/'server.stderr').open('wb')
  try:self.server=subprocess.Popen([self.plan['network']['python_executable'],str(ROOT/'tools/openmitrastar_l2_speed_server.py'),'--bind','192.168.1.49','--port','8081','--mib','4','--max-upload-mib','4','--allowed-client',ip],stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  finally:stdout.close();stderr.close()
  self.host.children.append(self.server);end=time.monotonic()+8
  while time.monotonic()<end:
   require(self.server.poll() is None,'client_server_failed')
   if b'OML2_HTTP_READY' in (self.out/'server.stdout').read_bytes():return
   time.sleep(.1)
  raise ClientError('client_server_not_ready')
 def run(self):
  self.out.mkdir(parents=True,exist_ok=False);result=dict(status='FAILED_F367_CLIENT',run_id=self.run_id);client_ip=None;before=None;after=None;error=None
  try:
   require(self.host.installed_receipt['image_sha256']==self.plan['images']['f367']['sha256'] and self.host.installed_receipt['same_hardware_lease'],'active_installation_receipt')
   identity=self.host.identity('f367');require(identity['boot_id']==self.host.installed_receipt['boot_id'],'client_boot_changed')
   current=self.host.snapshot();require(current['channel']==52 and current['filter_bw']==20 and current['cac_done']==current['ready']==current['tx_admission']==1 and current['nop_active']==current['cac_active']==0 and current['generation']==self.ready['generation'],'client_ap_not_ready')
   self.stage_payload();self.capture_attempted=True;result['capture']=self.action('Capture')
   initial=self.snapshot();self.bind_private(initial['target_bssid_tag']);result['connect']=self.action('Connect')
   before=self.snapshot();client=self.remote_json('client.json');client_ip=client['wifi_ipv4']
   require(any(row['tag']==client['client_tag'] and all(row[k] for k in ('auth','assoc','authorized')) for row in before['stations']),'client_not_authorized')
   self.start_server(client_ip);result['traffic']=self.action('Traffic');after=self.snapshot()
  except Exception as caught:error=caught;result['error']=str(caught) if isinstance(caught,(ClientError,ValueError)) else type(caught).__name__
  finally:
   if self.capture_attempted:
    try:result['restore_phase']=self.action('Restore')
    except Exception as caught:result['restore_error']=type(caught).__name__;error=error or caught
   if self.server:
    try:
     if self.server.poll() is None:self.server.terminate()
     try:self.server.wait(timeout=3)
     except subprocess.TimeoutExpired:self.server.kill();self.server.wait(timeout=3)
     require(self.server.poll() is not None,'client_server_containment_unproven')
     result['server_contained']=True
    except Exception as caught:
     result['server_cleanup_error']=type(caught).__name__;error=error or caught
   if self.firewall_created:
    try:self.firewall(client_ip,False);result['firewall_removed']=True
    except Exception as caught:result['firewall_cleanup_error']=type(caught).__name__;error=error or caught
   if not error:
    try:
     client=self.remote_json('client.json');result.update(harness.evaluate(self.config,client,before,after));result['client']=client;result['router_before']=before;result['router_after']=after
    except Exception as caught:error=caught;result['error']=type(caught).__name__
   (self.out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
  if error:raise ClientError('client_gate_failed') from None
  return dict(status=result['status'],result=str(self.out/'result.json'),sha256=harness.sha(self.out/'result.json'),run_id=self.run_id)

def run(host,plan,out,ready):return Dispatcher(host,plan,out,ready).run()

def preflight(host,plan):
 """Read-only client prerequisite before any F367 flash or 30-minute wait."""
 dispatcher=Dispatcher(host,plan,host.out/'unused-client-preflight',{})
 script=r'''$ErrorActionPreference='Stop'
if($env:COMPUTERNAME -cne 'APELSITO' -or $env:USERNAME -ine 'aelita'){throw 'identity'}
$parts=@($env:SSH_CONNECTION -split ' ')
if($parts.Count -ne 4 -or $parts[0] -cne '192.168.1.49' -or $parts[2] -cne '192.168.1.63'){throw 'wired-ssh'}
$eth=Get-NetAdapter -InterfaceIndex 6;$wifi=Get-NetAdapter -InterfaceIndex 17
if($eth.Name -cne 'Ethernet' -or $eth.Status -cne 'Up' -or $wifi.Name -cne 'Wi-Fi'){throw 'interfaces'}
$ip=Get-NetIPAddress -InterfaceIndex 6 -IPAddress '192.168.1.63' -AddressFamily IPv4
if([string]$ip.AddressState -cne 'Preferred' -or [string](Get-NetIPInterface -InterfaceIndex 6 -AddressFamily IPv4).Dhcp -cne 'Disabled'){throw 'control-address'}
foreach($index in @(6,17)){$row=Get-NetIPInterface -InterfaceIndex $index -AddressFamily IPv4;if([string]$row.WeakHostSend -cne 'Disabled' -or [string]$row.WeakHostReceive -cne 'Disabled'){throw 'strong-host'}}
'{"status":"PASS_F367_CLIENT_READONLY_PREFLIGHT","control_interface_index":6,"wifi_interface_index":17,"network_mutations":false}'
'''
 row=json.loads(dispatcher.ps(script,timeout=30));require(row.get('status')=='PASS_F367_CLIENT_READONLY_PREFLIGHT','client_preflight')
 return row
