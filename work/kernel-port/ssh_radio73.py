"""Pinned current HGW SSH; never refresh identity from network or log credentials."""
from pathlib import Path
import socket,sys,time,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'work/pydeps'))
import paramiko
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
def execute(command,input_bytes=None,host='192.168.1.91',timeout=30):
 if host not in ['192.168.1.90','192.168.1.91']:raise ValueError('Unknown HGW target')
 expected=(DEVICE/'dropbear_ed25519_host_key.pub').read_text().split()[0:2]
 sock=socket.create_connection((host,22),timeout=5);transport=paramiko.Transport(sock)
 try:
  transport.start_client(timeout=10);key=transport.get_remote_server_key()
  if key.get_name()!=expected[0] or key.get_base64()!=expected[1]:raise RuntimeError('Pinned HGW key mismatch')
  transport.auth_publickey('root',paramiko.Ed25519Key.from_private_key_file(str(Path.home()/'.ssh/id_ed25519')))
  if not transport.is_authenticated():raise RuntimeError('Owner SSH key refused')
  channel=transport.open_session(timeout=8);channel.settimeout(timeout);channel.exec_command(command)
  if input_bytes is not None:channel.sendall(input_bytes)
  channel.shutdown_write();stdout=bytearray();stderr=bytearray();deadline=time.monotonic()+timeout
  while not channel.exit_status_ready() or channel.recv_ready() or channel.recv_stderr_ready():
   if time.monotonic()>deadline:raise TimeoutError('Finite HGW SSH command expired')
   if channel.recv_ready():stdout+=channel.recv(65536)
   if channel.recv_stderr_ready():stderr+=channel.recv_stderr(4096)
   if len(stdout)+len(stderr)>4*1024*1024:raise RuntimeError('SSH output bound exceeded')
   time.sleep(.01)
  return {'exit_code':channel.recv_exit_status(),'stdout':stdout.decode(),'stderr':stderr.decode(),'host_key_sha256':hashlib.sha256(key.asbytes()).hexdigest(),'server_version':transport.remote_version}
 finally:transport.close()
