"""Prepare/evaluate an F367 client bundle locally. There is no execute command."""
from __future__ import annotations
import argparse,ast,copy,hashlib,ipaddress,json,re,secrets
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
import aelita_ssh_policy as ssh_policy

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'configs/f367_aelita_client.json'
WPA=ROOT/'tools/run_aelita_2g_wpa2_runtime_psk_once.py'
REUSED=('Get-CurrentSsid','Get-CurrentBssid','Wait-Ssid','Read-RuntimePsk','New-Wpa2ProfileXml')

def require(value,message):
 if not value:raise ValueError(message)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def reused_functions():
 tree=ast.parse(WPA.read_text(encoding='utf-8'))
 worker=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='WORKER_PS1' for t in node.targets))
 parts=[]
 for name in REUSED:
  start=worker.index('function '+name+' {')
  # The last selected function is followed by the worker body, not a function.
  if name=='New-Wpa2ProfileXml':end=worker.index('\n$outputDirectory =',start)
  else:end=worker.index('\nfunction ',start+1)
  parts.append(worker[start:end].strip())
 return '\n\n'.join(parts)+'\n'

def validate_config(config):
 require(config['schema']=='openmitrastar.f367-aelita-client-config/v1','config_schema')
 c=config['client'];require(c['computer']=='APELSITO' and c['user']=='aelita' and c['control_ipv4']=='192.168.1.63' and c['control_interface_index']==6 and c['wifi_interface_index']==17 and c['ssh_host_key_mode']=='pinned','client_scope')
 require(config['controller']==dict(computer='APPLESITO',ipv4='192.168.1.49'),'controller_scope')
 require(config['router']==dict(ipv4='192.168.1.90',interface='wifi0',channel=52,bandwidth_mhz=20),'router_scope')
 require(config['restore']['capture_current_profile'] is True and config['restore']['watchdog_seconds']==240,'restoration_scope')
 t=config['traffic'];require(t['bytes_each_direction']==4*1024*1024 and 10<=t['timeout_seconds']<=30,'traffic_bounds')
 for field,path in [('download_url','/speed.bin'),('upload_url','/upload.bin')]:
  u=urlsplit(t[field]);require(u.scheme=='http' and u.hostname=='192.168.1.49' and u.port==8081 and u.path==path and not u.username and not u.password and not u.query and not u.fragment,'lan_endpoint_scope')
 u=urlsplit(t['internet_url']);require(u.scheme=='https' and u.hostname=='www.microsoft.com' and u.path=='/' and not u.username and not u.password and not u.query and not u.fragment,'internet_endpoint_scope')
 return config

def future_binding(config):
 if not all(config.get(k) for k in ('image','installed_proof','ap_ready_proof')):return False
 image=config['image'];require(re.fullmatch(r'lyoko-[A-Za-z0-9_.-]*-f367[A-Za-z0-9_.-]*',image['version']) is not None,'future_version')
 for row in (image,config['installed_proof'],config['ap_ready_proof']):require(Path(row['path']).is_file() and sha(row['path'])==row['sha256'],'future_evidence_hash')
 require(Path(image['path']).stat().st_size==image['bytes'],'future_image_bytes')
 qref=image['qualification'];require(sha(qref['path'])==qref['sha256'],'future_qualification_hash');q=json.loads(Path(qref['path']).read_text(encoding='ascii'))
 require(q['status'].startswith('PASS_OFFLINE_') and q['artifact']['sha256']==image['sha256'] and q['artifact']['bytes']==image['bytes'] and q['product_version']==image['version'],'future_qualification_binding')
 installed=json.loads(Path(config['installed_proof']['path']).read_text(encoding='ascii'))
 require(installed['status']=='PASS_F367_PRESERVED_JOURNAL' and installed['writer']['image']==image['sha256'] and installed['writer']['byte_compare'] is True and installed['containment_confirmed'] is True and installed['retain_lease_required'] is False,'future_installation_PASS')
 # This is an integration receipt from the root-owned AP/CAC campaign, not a
 # substitute for its detector readiness/CAC/NOP or fresh live checks.
 ap=json.loads(Path(config['ap_ready_proof']['path']).read_text(encoding='ascii'))
 require(ap['schema']=='openmitrastar.f367-ap-client-readiness/v1' and ap['image_sha256']==image['sha256'] and ap['channel']==52 and ap['bandwidth_mhz']==20 and ap['cac_complete'] is True and ap['detector_ready'] is True and ap['tx_allowed'] is True and ap['boot_id']==installed['f367_identity']['boot_id'],'future_ap_readiness')
 return True

def evaluate(config,client,router_before,router_after):
 """Require same-run per-station authorization and strong-host Wi-Fi traffic."""
 validate_config(config)
 require(config.get('image') is not None,'image_binding_missing')
 run=client['run_id'];require(re.fullmatch('[0-9a-f]{32}',run) is not None,'run_id')
 require(router_before['run_id']==router_after['run_id']==run and router_before['boot_id']==router_after['boot_id'] and router_before['firmware']==router_after['firmware']==config['image']['version'],'router_epoch')
 require(client['control_verified'] is True and client['control_unchanged'] is True and client['control_interface_index']==6 and client['wifi_interface_index']==17 and client['strong_host'] is True,'independent_control')
 ip=client['wifi_ipv4'];require(ipaddress.ip_address(ip) in ipaddress.ip_network('192.168.1.0/24') and ip not in ('192.168.1.1','192.168.1.49','192.168.1.63','192.168.1.90'),'wifi_source')
 require(client['associated'] is True and client['bssid_match'] is True and client['channel']==52,'target_association')
 tag=client['client_tag'];require(re.fullmatch('[0-9a-f]{64}',tag) is not None,'client_tag')
 for row in (router_before,router_after):
  stations=[station for station in row['stations'] if station['tag']==tag]
  require(len(stations)==1 and all(stations[0][key] is True for key in ('auth','assoc','authorized')),'client_authorization')
 require(router_after['wifi_rx_bytes']>router_before['wifi_rx_bytes'] and router_after['wifi_tx_bytes']>router_before['wifi_tx_bytes'],'router_bidirectional_bytes')
 for direction in ('download','upload','internet'):
  t=client[direction];require(t['exit_code']==0 and t['local_ip']==ip and t['http_code']==200,'source_bound_'+direction)
  if direction!='internet':require(t['bytes']==config['traffic']['bytes_each_direction'] and t['remote_ip']=='192.168.1.49','transfer_'+direction)
  else:require(ipaddress.ip_address(t['remote_ip']).is_global,'internet_remote')
 require(client['restore']['profile_restored'] is True and client['restore']['profile_unchanged'] is True and client['restore']['test_profile_removed'] is True and client['restore']['control_unchanged'] is True,'restoration')
 return dict(status='PASS_F367_CLIENT_SOURCE_BOUND_TRAFFIC',run_id=run,download_bytes=client['download']['bytes'],upload_bytes=client['upload']['bytes'],internet='HTTPS_HEAD_FROM_WIFI',secrets_logged=False,client_macs_logged=False)

def parse_router_snapshot(text):
 rows=text.strip().splitlines();require(rows and rows[0].startswith('OMF367_ROUTER '),'router_snapshot_header')
 header=dict(token.split('=',1) for token in rows[0].split()[1:]);require(set(header)=={'run_id','firmware','boot_id','wifi_rx_bytes','wifi_tx_bytes','target_bssid_tag'},'router_snapshot_fields')
 require(re.fullmatch('[0-9a-f]{32}',header['run_id']) is not None and re.fullmatch('[0-9a-f]{64}',header['target_bssid_tag']) is not None,'router_snapshot_tags')
 header['wifi_rx_bytes']=int(header['wifi_rx_bytes']);header['wifi_tx_bytes']=int(header['wifi_tx_bytes']);header['stations']=[]
 for line in rows[1:]:
  require(line.startswith('OMF367_STATION '),'station_header');fields=dict(token.split('=',1) for token in line.split()[1:]);require(set(fields)=={'tag','auth','assoc','authorized'} and re.fullmatch('[0-9a-f]{64}',fields['tag']) is not None,'station_fields')
  require(all(fields[k] in ('0','1') for k in ('auth','assoc','authorized')),'station_flags');header['stations'].append(dict(tag=fields['tag'],**{k:fields[k]=='1' for k in ('auth','assoc','authorized')}))
 return header

def prepare(config,out,config_path=CONFIG):
 validate_config(config);bound=future_binding(config)
 c=config['client'];require((ROOT/c['key']).is_file(),'canonical_key_missing')
 ssh_policy.ensure_known_host(c['control_ipv4'],ROOT/c['known_hosts'],mode='pinned')
 out.mkdir(parents=True,exist_ok=False)
 bundle=copy.deepcopy(config);bundle['run_id']=secrets.token_hex(16);bundle['image_bound']=bound;bundle['execution_allowed']=False
 bundle['pending_live_inputs']=['fresh pinned HGW version/boot/CAC receipt','private test SSID and runtime PSK over SSH stdin/DPAPI','salted target BSSID tag from same HGW wifi0','fresh wired SSH address/interface/strong-host verification','SYSTEM restore probe PASS before connect','root orchestration of ARM/connect/authorized/transfer/finally restoration']
 (out/'config.json').write_text(json.dumps(bundle,indent=2)+'\n',encoding='ascii')
 (out/'reused-wlan-functions.ps1').write_text(reused_functions(),encoding='utf-8',newline='\n')
 for name in ('f367_aelita_client.ps1','f367_aelita_router_snapshot.sh'):(out/name).write_bytes((ROOT/'tools'/name).read_bytes())
 sources=[config_path,WPA,Path(__file__),ROOT/'tools/f367_aelita_client.ps1',ROOT/'tools/f367_aelita_router_snapshot.sh',ROOT/'tools/aelita_ssh_policy.py',ROOT/'tools/openmitrastar_l2_speed_server.py',ROOT/'tools/test_f367_aelita_harness.py',ROOT/config['reference'],ROOT/c['known_hosts']]
 result=dict(status='PREPARED_OFFLINE_F367_CLIENT_HARNESS',image_bound=bound,execution_allowed=False,hardware_actions=False,source_sha256={str(p):sha(p) for p in sources},bundle_sha256={p.name:sha(p) for p in out.iterdir()},reused_functions=list(REUSED),existing_server='tools/openmitrastar_l2_speed_server.py',reference_scope='AELITA through main router only; not HGW client acceptance')
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
 return dict(status=result['status'],bundle=str(out),image_bound=bound,execution_allowed=False,hardware_actions=False)

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--config',type=Path,default=CONFIG);p.add_argument('--output-dir',type=Path);a=p.parse_args()
 config=json.loads(a.config.read_text(encoding='ascii'));out=a.output_dir or ROOT/'outputs/preflight'/('f367-aelita-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));print(json.dumps(prepare(config,out,a.config),indent=2))

if __name__=='__main__':main()
