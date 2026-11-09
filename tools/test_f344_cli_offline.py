"""Exercise native wpa_cli built from the same OEM source on private fake sockets."""
from pathlib import Path
import argparse,json,socket,subprocess,tempfile,threading
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--cli',type=Path,required=True);ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();cases=[]
 for command,request,reply in [
  ('status',b'STATUS',b'bssid=02:00:00:00:00:01\nssid=F344-SYNTHETIC\nkey_mgmt=WPA2-PSK\nwpa_state=COMPLETED\n'),
  ('terminate',b'TERMINATE',b'OK\n'),('ping',b'PING',b'PONG\n'),('status',b'STATUS',b'FAIL\n')]:
  with tempfile.TemporaryDirectory(prefix='f344-ctrl-') as tmp:
   server=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);server.bind(str(Path(tmp)/'wifi0'));server.settimeout(5);seen=[];errors=[]
   def answer():
    try:
     data,address=server.recvfrom(4096);seen.append(data);server.sendto(reply,address)
    except Exception as e:errors.append(type(e).__name__)
   thread=threading.Thread(target=answer);thread.start()
   try:process=subprocess.run([str(a.cli),'-p',tmp,'-i','wifi0',command],capture_output=True,timeout=10)
   finally:thread.join(timeout=6);server.close()
   assert not thread.is_alive() and not errors,(errors,seen)
   assert seen==[request],seen
   assert reply.strip() in process.stdout,(process.returncode,process.stdout,process.stderr)
   if reply!=b'FAIL\n':assert process.returncode==0
   cases.append({'command':request.decode(),'private_socket_selected':True,'exact_request':True,'response_observed':True,'exit_code':process.returncode,'negative_response':reply==b'FAIL\n'})
 report={'schema':'openmitrastar.f344-cli-offline-tests/v1','status':'PASS_NATIVE_CLI_SYNTHETIC_CONTROL','cases':cases,
  'execution_architecture':'native build of exact OEM source; ARC execution UNRUN',
  'hardware_actions':False,'wifi_or_rf_tests':False,'real_supplicant_daemon_started':False,'negative_reply_exit_code':cases[-1]['exit_code'],
  'rule':'Check the daemon response and actual driver readback; process exit alone is not state acceptance.'}
 a.result.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'cases':len(cases),'negative_reply_exit_code':cases[-1]['exit_code']}))
if __name__=='__main__':main()
