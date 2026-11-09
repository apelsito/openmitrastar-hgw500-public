"""Eight focused local integration cases. Fake MTD/backend; no device actions."""
from pathlib import Path
import argparse,hashlib,json,os,struct,subprocess,zlib
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--reader',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
 overlay=a.source/'overlay';base=a.source/'base';persist=overlay/'usr/sbin/om-config-persist';settings=overlay/'usr/libexec/openmitrastar/f361-settings';cases=[]
 for p in [persist,settings]:
  import re
  assert not re.search(r'\b(?:mktemp|rmdir|cmp|tr)\b',p.read_text()),'unsupported BusyBox dependency'
 keys='CONFIG_SCHEMA HOSTNAME PRODUCT_MODE SSH_ENABLE SSH_PORT API_ENABLE API_PORT LOG_SIZE_KB LOG_ROTATIONS MANAGEMENT_STATICIP MANAGEMENT_IPV4 MANAGEMENT_NETMASK MANAGEMENT_GATEWAY MANAGEMENT_DNS MANAGEMENT_RECOVERY_IPV4 RADIO2G_ENABLE RADIO2G_SSID RADIO2G_COUNTRY RADIO2G_CHANNEL RADIO2G_BRIDGE RADIO2G_EAPOL_TRACE RADIO2G_EAPOL_MGNT_QUEUE RADIO5G_ENABLE ORIGIN_MTD5_IMPORTED RADIO5G_SSID RADIO5G_CONFIG_SOURCE'.split()
 vals=['1','lab-router','ap','1','22','1','8080','64','2','1','192.168.1.90','255.255.255.0','192.168.1.1','192.168.1.1','192.168.1.200','1','Lab2','ES','1','1','0','0','1','1','Trusted5','origin-mtd5-validated'];normal=dict(zip(keys,vals))
 def payload(v):return ''.join(k+'='+v[k]+'\n' for k in keys).encode()
 def journal(data):
  head=bytearray(32);head[4:8]=b'F342';head[8]=1;head[10]=32;struct.pack_into('<I',head,12,len(data));struct.pack_into('<Q',head,16,1);struct.pack_into('<I',head,24,zlib.crc32(data)&0xffffffff);struct.pack_into('<I',head,28,zlib.crc32(head[4:28])&0xffffffff)
  return bytes(head)+data+b'\xff'*(131072-32-len(data))
 def setup(name,data=None):
  d=a.out/name;d.mkdir();run=d/'run';active=d/'active.conf';active.write_bytes(payload(normal));store=d/'store.bin';store.write_bytes(journal(payload(normal)) if data is None else data)
  origin=d/'origin.conf';origin.write_bytes(b'ORIGIN_MTD5_IMPORTED=1\nRADIO5G_SSID=Trusted5\n');feature=d/'feature';feature.write_text('OPENMITRASTAR_CONFIG_PERSIST=1\n')
  module=d/'module/parameters';module.mkdir(parents=True);(module/'allow_hw').write_text('Y\n');(module/'allow_program').write_text('Y\n')
  normalizer=d/'normalizer';normalizer.write_text('#!/bin/sh\nexec /bin/sh '+str(base/'usr/sbin/om-config-prepare')+' "$@"\n');normalizer.chmod(0o755)
  cli=d/'cli';cli.write_text('''#!/usr/bin/python3
from pathlib import Path
import sys,os,json
d=Path(os.environ['FAKE_BACKEND'])
with (d/'calls').open('a') as f:f.write(sys.argv[1]+'\\n')
if sys.argv[1]=='save':
 data=sys.stdin.buffer.read()
 if os.environ.get('FAKE_FAIL')=='1':sys.exit(1)
 (d/'saved').write_bytes(data)
 print(json.dumps({'status':'saved','sequence':2,'slot':1,'bytes':len(data)},separators=(',',':')))
elif sys.argv[1]=='load':sys.stdout.buffer.write((d/'saved').read_bytes())
else:sys.exit(9)
''');cli.chmod(0o755)
  env=dict(os.environ,OM_F361_TEST_MODE='1',OM_F361_RUN=str(run),OM_F361_ACTIVE=str(active),OM_F361_ORIGIN=str(origin),OM_F361_DEFAULTS=str(active),OM_F361_NORMALIZER=str(normalizer),OM_F361_SETTINGS=str(settings),OM_F361_READER=str(a.reader),OM_F361_CLI=str(cli),OM_F361_FEATURE=str(feature),OM_F361_MODULE_ROOT=str(d/'module'),OM_F361_CLI_SHA=sha(cli),F361_TEST_STORE=str(store),FAKE_BACKEND=str(d))
  return d,run,store,env
 def call(env,action,code=0):
  p=subprocess.run(['/bin/sh',str(persist),action],env=env,capture_output=True,timeout=10)
  assert p.returncode==code,action+' returned unexpected code'
  assert not (Path(env['OM_F361_RUN'])/'lock').exists(),'lock leaked'
  return p
 d,run,store,env=setup('valid');before=sha(store);call(env,'boot');assert (run/'ready').read_text().strip()=='F361_READY';restored=(run/'restore/v1/settings.conf').read_text();assert len(restored.splitlines())==22 and 'ORIGIN_' not in restored and 'RADIO5G_SSID' not in restored;assert sha(store)==before;cases.append('valid-journal-settings22-no-write-lock-clean')
 for name,data in [('empty',b'\xff'*131072),('corrupt',journal(payload(normal))[:40]+b'X'+journal(payload(normal))[41:])]:
  d,run,store,env=setup(name,data);before=sha(store);call(env,'boot');assert not (run/'ready').exists() and sha(store)==before;cases.append(name+'-fallback-no-format-lock-clean')
 forged=dict(normal,ORIGIN_MTD5_IMPORTED='0',RADIO5G_SSID='UNTRUSTED',RADIO5G_CONFIG_SOURCE='untrusted')
 d,run,store,env=setup('derived',journal(payload(forged)));call(env,'boot');assert (run/'ready').exists();assert 'UNTRUSTED' not in (run/'restore/v1/settings.conf').read_text();cases.append('derived-fields-discarded-trusted-origin-only')
 bad=dict(normal,SSH_PORT='0');d,run,store,env=setup('bad-settings',journal(payload(bad)));before=sha(store);call(env,'boot');assert not (run/'ready').exists() and sha(store)==before;cases.append('invalid-managed-setting-fallback')
 d,run,store,env=setup('save');p=call(env,'commit');assert p.stdout.startswith(b'OMCONFIG_STORE_COMMIT_PASS slot=B sequence=2 sha256=');assert (d/'saved').read_bytes()==payload(normal) and (d/'calls').read_text().splitlines()==['save','load'];assert not (d/'run/lock').exists();cases.append('explicit-save-load-equal-no-reset-lock-clean')
 d,run,store,env=setup('save-failure');env['FAKE_FAIL']='1';p=call(env,'commit',1);assert b'save-failed-no-retry' in p.stderr and (d/'calls').read_text().splitlines()==['save'];cases.append('save-error-no-retry-lock-clean')
 d,run,store,env=setup('api');api=(overlay/'usr/libexec/openmitrastar/om-api-v1').read_text();part=api[api.index('run_config_store_action()'):api.index('\navailable_packages_json()')]
 action=d/'action';action.write_text('#!/bin/sh\nexec /bin/sh '+str(persist)+' "$@"\n');action.chmod(0o755)
 wrapper=d/'api.sh';wrapper.write_text('require_mutation(){ :; }\nheaders(){ printf "Content-Type: application/json\\n\\n"; }\njstr(){ printf \'"%s"\' "$1"; }\nerror_json(){ printf \'{"error":"%s"}\\n\' "$2"; }\nconfig_store='+str(action)+'\n'+part+'\nrun_config_store_action\n')
 env.update(CONTENT_LENGTH='13',HTTP_X_OM_CONFIRM='OPENMITRASTAR_CONFIG_STORE_V1');p=subprocess.run(['/bin/sh',str(wrapper)],input=b'action=commit',env=env,capture_output=True,timeout=10)
 assert p.returncode==0 and b'"persistent":true' in p.stdout and b'"managed_settings":22' in p.stdout and (d/'calls').read_text().splitlines()==['save','load'];assert not (run/'lock').exists();cases.append('actual-api-store-commit-routes-to-new-backend')
 result={'schema':'openmitrastar.f361-integration-tests/v1','status':'PASS','cases':cases,'count':len(cases),'hardware_actions':False,'watchdog_actions':False,'radio_actions':False,'store_write_backend':'fake local CLI only'}
 (a.out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'PASS','cases':len(cases),'result':str(a.out/'result.json')}))
if __name__=='__main__':main()
