"""Stage exact MIME binary and test TLS8443 before replacing activeHTTPS443."""
from pathlib import Path
import hashlib,json,ssl,subprocess,time
from http.client import HTTPSConnection
from ssh_radio73 import execute,ROOT,DEVICE
PIN='43a0fea8072cfd725ae5803bc7fc4bfd94bb734d8a321b8490945d9563c62d1c'
def main():
 out=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/uhttpd73-mime-v42'
 if out.exists():raise ValueError('Immutable evidence exists')
 out.mkdir()
 data=subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','--','python3','-c',"import pathlib,sys;sys.stdout.buffer.write(pathlib.Path('/home/rea/openmitrastar-linux73-20261022T135100Z/uhttpd73-wasm-mime-v1/a/uhttpd').read_bytes())"],capture_output=True,check=True).stdout
 assert hashlib.sha256(data).hexdigest()==PIN
 staged=execute("test ! -e /run/uhttpd73-wasm && umask 077 && cat > /run/uhttpd73-wasm",data,timeout=15)
 assert staged['exit_code']==0
 check=execute("sha256sum /run/uhttpd73-wasm; chmod 700 /run/uhttpd73-wasm")
 assert check['exit_code']==0 and check['stdout'].startswith(PIN)
 common='-f -c /run/om73-web.conf -h /www -C /etc/lyoko/tls/server.pem -K /etc/lyoko/tls/server.key -D -S -I index.cgi -x /api/v1 -i .cgi=/bin/sh -n 2 -N 8 -t 15 -T 20'
 launch=execute("/run/uhttpd73-wasm "+common+" -s 0.0.0.0:8443 >/run/uhttpd73-test.log 2>&1 </dev/null & echo MIME_TEST_PID=$!")
 ctx=ssl.create_default_context(cafile=str(DEVICE/'firmware/radioeth73-events-ram-20261022T2036Z/server.pem'))
 rows=[]
 def fetch(port):
  c=HTTPSConnection('192.168.1.91',port,context=ctx,source_address=('192.168.1.49',0),timeout=15)
  try:
   c.request('GET','/Doom/chocolate-doom.wasm');r=c.getresponse();body=r.read(2300000)
   row={'port':port,'status':r.status,'mime':r.getheader('Content-Type'),'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
   rows.append(row);assert r.status==200 and row['mime']=='application/wasm' and row['sha256']=='eb47045e861708f4263f994610ed2e58ab63838aff738e3577cca9b68797c20e'
  finally:c.close()
 error=None;switched=False
 try:
  time.sleep(.4);fetch(8443)
  # Exact activePID289 was observed; refresh executable identity before TERM.
  identity=execute("test \"$(cat /proc/289/comm)\" = uhttpd && tr '\\0' ' ' < /proc/289/cmdline")
  assert identity['exit_code']==0 and identity['stdout'].startswith('/usr/sbin/uhttpd -f -c /run/om73-web.conf')
  execute("kill -TERM 289; sleep 1")
  switched=True
  final=execute("/run/uhttpd73-wasm "+common+" -s 0.0.0.0:443 >/run/uhttpd73-current.log 2>&1 </dev/null & echo MIME_CURRENT_PID=$!")
  time.sleep(.5);fetch(443)
 except BaseException as e:
  error=type(e).__name__
  if switched:execute("/usr/sbin/uhttpd "+common+" -s 0.0.0.0:443 >/run/uhttpd73-restore.log 2>&1 </dev/null &")
  raise
 finally:
  result={'status':'PASS_DEVICE_WASM_MIME_HTTPS' if error is None else 'MIME_TRIAL_INCOMPLETE','candidate_sha256':PIN,'rows':rows,'launch':launch,'current':locals().get('final'),'error':error,'flash':False,'bootenv':False,'persistent':False}
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
