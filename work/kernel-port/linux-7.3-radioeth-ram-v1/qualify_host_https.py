"""Build the same current server sources for host TLS interoperability tests.

Local loopback HTTPS only, no router access or system install. Test certificates
are confined to this evidence directory. ARC runtime acceptance stays separate.
"""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,socket,ssl,subprocess,time
from http.client import HTTPSConnection

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(command,log,env):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=900)

def main():
 p=argparse.ArgumentParser()
 for name in ['arc-build','wolf-build','extra-inputs','cmake','output']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);prefix=a.output/'install';prefix.mkdir()
 sources={}
 for name in ['wolfssl','json-c','libubox','ustream-ssl','uhttpd']:
  original=a.wolf_build/'source' if name=='wolfssl' else a.arc_build/'sources'/name
  target=a.output/'sources'/name;target.parent.mkdir(exist_ok=True);shutil.copytree(original,target);sources[name]=target
 # The ARC adapter is target-specific; host GCC emits its own 32-bit atomic
 # instructions. All portable source bodies remain equal to the ARC build.
 file=sources['libubox']/'CMakeLists.txt';text=file.read_text();assert text.count('LIST(APPEND SOURCES arc750_atomic32.c)')==1
 file.write_text(text.replace('LIST(APPEND SOURCES arc750_atomic32.c)\n',''))
 env=os.environ|{'SOURCE_DATE_EPOCH':'1792694400','LC_ALL':'C','PKG_CONFIG_LIBDIR':str(prefix/'lib/pkgconfig'),'PKG_CONFIG_PATH':str(prefix/'lib/pkgconfig')}
 flags='-Os -ffunction-sections -fdata-sections -fstack-protector-strong'
 choices=[('wolfssl',['-DBUILD_SHARED_LIBS=ON','-DWOLFSSL_ASM=no','-DWOLFSSL_SINGLE_THREADED=yes','-DWOLFSSL_OPENSSLEXTRA=yes','-DWOLFSSL_OPENSSLALL=no','-DWOLFSSL_TLS13=yes','-DWOLFSSL_TLSV12=yes','-DWOLFSSL_OLD_TLS=no','-DWOLFSSL_TLSV10=no','-DWOLFSSL_EXAMPLES=no','-DWOLFSSL_CRYPT_TESTS=no','-DWOLFSSL_MLKEM=no','-DWOLFSSL_DH=const','-DWOLFSSL_WPAS=yes','-DWOLFSSL_TLSX=yes','-DWOLFSSL_EX_DATA=yes']),
  ('json-c',['-DBUILD_SHARED_LIBS=ON','-DBUILD_STATIC_LIBS=ON','-DBUILD_TESTING=OFF','-DENABLE_THREADING=OFF','-DENABLE_RDRAND=OFF','-DDISABLE_WERROR=ON']),
  ('libubox',['-DBUILD_LUA=OFF','-DBUILD_EXAMPLES=OFF','-DUNIT_TESTING=OFF']),
  ('ustream-ssl',['-DWOLFSSL=ON','-DMBEDTLS=OFF']),
  ('uhttpd',['-DTLS_SUPPORT=ON','-DLUA_SUPPORT=OFF','-DUBUS_SUPPORT=OFF','-DUCODE_SUPPORT=OFF'])]
 for name,options in choices:
  build=a.output/('build-'+name)
  run([str(a.cmake),'-S',str(sources[name]),'-B',str(build),'-G','Unix Makefiles','-DCMAKE_BUILD_TYPE=MinSizeRel','-DCMAKE_INSTALL_PREFIX='+str(prefix),'-DCMAKE_INSTALL_LIBDIR=lib','-DCMAKE_PREFIX_PATH='+str(prefix),'-DCMAKE_C_FLAGS='+flags,'-DCMAKE_EXE_LINKER_FLAGS=-Wl,--gc-sections,-z,relro,-z,now','-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--gc-sections,-z,relro,-z,now']+options,a.output/(name+'-config.log'),env)
  run([str(a.cmake),'--build',str(build),'--parallel','2'],a.output/(name+'-build.log'),env)
  run([str(a.cmake),'--install',str(build)],a.output/(name+'-install.log'),env)
 root=a.output/'www';root.mkdir();static=bytes(range(256))*256;(root/'integrity.bin').write_bytes(static)
 (root/'probe.cgi').write_text('#!/bin/sh\nprintf "Content-Type: application/json\\r\\nCache-Control: no-store\\r\\n\\r\\n"\nprintf \'{"https":"%s","csrf":"%s"}\\n\' "${HTTPS:-unset}" "${HTTP_X_OM_CSRF:-unset}"\n');(root/'probe.cgi').chmod(0o755)
 cert=a.output/'server.pem';key=a.output/'server.key'
 run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-sha256','-nodes','-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1','-keyout',str(key),'-out',str(cert)],a.output/'test-certificate.log',env);key.chmod(0o600)
 sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
 server_env=env|{'LD_LIBRARY_PATH':str(prefix/'lib')}
 checks={};evidence=[];server=None
 try:
  log=(a.output/'server.log').open('xb')
  server=subprocess.Popen([str(prefix/'bin/uhttpd'),'-f','-s','127.0.0.1:'+str(port),'-h',str(root),'-C',str(cert),'-K',str(key),'-D','-S','-i','.cgi=/bin/sh','-n','2','-N','8'],stdout=log,stderr=log,env=server_env)
  deadline=time.monotonic()+10
  while time.monotonic()<deadline:
   if server.poll() is not None:raise RuntimeError('Host HTTPS process ended before test')
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
   except OSError:time.sleep(.05)
  else:raise TimeoutError('Host HTTPS listener not ready')
  for version in [ssl.TLSVersion.TLSv1_2,ssl.TLSVersion.TLSv1_3]:
   context=ssl.create_default_context(cafile=str(cert));context.minimum_version=version;context.maximum_version=version
   connection=HTTPSConnection('127.0.0.1',port,context=context,timeout=5)
   try:
    connection.connect();negotiated=connection.sock.version();cipher=connection.sock.cipher()[0]
    connection.request('GET','/integrity.bin');response=connection.getresponse();body=response.read()
    checks[version.name+'_integrity']=response.status==200 and body==static
    evidence.append({'protocol':negotiated,'cipher':cipher,'status':response.status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()})
   finally:connection.close()
  context=ssl.create_default_context(cafile=str(cert));connection=HTTPSConnection('127.0.0.1',port,context=context,timeout=5)
  try:
   connection.request('GET','/probe.cgi',headers={'X-OM-CSRF':'host-fixture-token','HTTPS':'off','X-Forwarded-Proto':'http'});response=connection.getresponse();payload=json.loads(response.read())
   checks['cgi_https_server_derived']=response.status==200 and payload['https']=='on'
   checks['cgi_csrf_header_exact']=payload['csrf']=='host-fixture-token'
  finally:connection.close()
  # Verify rejection with a client using normal trust, not an ignore-cert flag.
  context=ssl.create_default_context();connection=HTTPSConnection('127.0.0.1',port,context=context,timeout=5)
  try:
   connection.connect();checks['untrusted_certificate_rejected']=False
  except ssl.SSLCertVerificationError:checks['untrusted_certificate_rejected']=True
  finally:connection.close()
  # Legacy TLS handshakes only, never cleartext HTTP. Library must reject them.
  for version in [ssl.TLSVersion.TLSv1,ssl.TLSVersion.TLSv1_1]:
   context=ssl.create_default_context(cafile=str(cert));context.minimum_version=version;context.maximum_version=version;context.set_ciphers('ALL:@SECLEVEL=0')
   connection=HTTPSConnection('127.0.0.1',port,context=context,timeout=5)
   try:connection.connect();checks[version.name+'_rejected']=False
   except (ssl.SSLError,ConnectionResetError):checks[version.name+'_rejected']=True
   finally:connection.close()
  result={'schema':'openmitrastar.current-web-host-https/v1','status':'PASS_HOST_TLS_AND_LYOKO_HEADERS' if all(checks.values()) else 'FAIL_HOST_HTTPS','checks':checks,'evidence':evidence,'hardware_accessed':False,'physical_arc':'UNRUN','server_source_sha256':sha(sources['uhttpd']/'proc.c'),'arc_server_source_sha256':sha(a.arc_build/'sources/uhttpd/proc.c'),'limits':['Host ABI/CPU test, not ARC loader or device TLS acceptance.','Complete LYOKO authentication/config transactions not exercised by this small CGI probe.']}
  assert result['server_source_sha256']==result['arc_server_source_sha256']
  (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));assert all(checks.values())
 finally:
  if server:
   server.terminate()
   try:server.wait(timeout=3)
   except subprocess.TimeoutExpired:server.kill();server.wait(timeout=3)
  if 'log' in locals():log.close()

if __name__=='__main__':main()
