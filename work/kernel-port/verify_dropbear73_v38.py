"""Pin persistent host public key and execute finite read-only SSH proof."""
from pathlib import Path
import hashlib,json,socket,sys,time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'work/pydeps'))
import paramiko
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
def main():
 out=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/dropbear73-ssh-v38'
 if out.exists():raise ValueError('Immutable evidence exists')
 out.mkdir();transport=None;result={'status':'SSH_GATE_INCOMPLETE','flash':False,'bootenv':False,'credentials_logged':False}
 try:
  expected=(DEVICE/'dropbear_ed25519_host_key.pub').read_text().split()[0:2]
  s=socket.create_connection(('192.168.1.91',22),timeout=6);transport=paramiko.Transport(s);transport.start_client(timeout=12)
  hostkey=transport.get_remote_server_key();assert hostkey.get_name()==expected[0] and hostkey.get_base64()==expected[1]
  key=paramiko.Ed25519Key.from_private_key_file(str(Path.home()/'.ssh/id_ed25519'))
  transport.auth_publickey('root',key);assert transport.is_authenticated()
  channel=transport.open_session(timeout=8);channel.settimeout(12)
  channel.exec_command('uname -r; /bin/busybox uptime; /bin/busybox cat /proc/net/dev')
  stdout=bytearray();stderr=bytearray();deadline=time.monotonic()+15
  while not channel.exit_status_ready() or channel.recv_ready() or channel.recv_stderr_ready():
   if time.monotonic()>deadline:raise TimeoutError('Finite SSH command expired')
   if channel.recv_ready():stdout+=channel.recv(65536)
   if channel.recv_stderr_ready():stderr+=channel.recv_stderr(4096)
   time.sleep(.02)
  code=channel.recv_exit_status();text=stdout.decode();assert code==0 and text.splitlines()[0]=='7.3.0-openmitrastar-radio73-v1'
  result.update(status='PASS_MODERN_PINNED_SSH_COMMAND',host_key_sha256=hashlib.sha256(hostkey.asbytes()).hexdigest(),server_version=transport.remote_version,cipher=transport.remote_cipher,exit_code=code,stdout=text,stderr=stderr.decode(),authentication='owner Ed25519 publickey',host_key_verified=True)
 except BaseException as e:result.update(error_type=type(e).__name__,error_reason=str(e));raise
 finally:
  if transport:transport.close()
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
