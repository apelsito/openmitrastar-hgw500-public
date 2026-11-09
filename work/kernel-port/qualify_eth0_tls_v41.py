"""Wait for the explicitly requested cable move; prove eth0 TLS and SSH."""
from pathlib import Path
import json,subprocess,socket,time,sys
from ssh_radio73 import execute,ROOT
def main():
 out=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-eth0-v41'
 if out.exists():raise ValueError('Immutable evidence exists')
 out.mkdir();deadline=time.monotonic()+300;found=False
 while time.monotonic()<deadline:
  try:
   with socket.create_connection(('192.168.1.90',22),timeout=.5):pass
   result=execute('uname -r; cat /run/om73-eth0-v40/state; cat /sys/class/net/eth0/carrier',host='192.168.1.90',timeout=8)
   if '7.3.0-openmitrastar-radio73-v1' in result['stdout'] and 'ETH0_TRIAL_ACTIVE' in result['stdout']:
    found=True;break
  except (OSError,RuntimeError):pass
  time.sleep(1)
 if not found:
  (out/'result.json').write_text(json.dumps({'status':'OWNER_ETH0_CABLE_WINDOW_NOT_OBSERVED','flash':False},indent=2));return
 (out/'ssh-binding.json').write_text(json.dumps(result,indent=2))
 config=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/radioeth73-events-ram-20261022T2036Z/CONFIG.json'
 boot=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-physical-powercycle-v15/result.json'
 command=[sys.executable,str(ROOT/'work/kernel-port/qualify_device_https_v13.py'),'--config',str(config),'--boot-receipt',str(boot),'--output',str(out/'tls'),'--host','192.168.1.90','--upload-fixture']
 r=subprocess.run(command,capture_output=True,text=True,timeout=160)
 (out/'tls.stdout').write_text(r.stdout);(out/'tls.stderr').write_text(r.stderr)
 tls=json.loads((out/'tls/result.json').read_text())
 final=execute('uname -r; cat /proc/net/dev; cat /sys/class/net/eth0/lyoko_emac_port_stats; cat /sys/class/net/eth0/lyoko_emac_txdiag',host='192.168.1.90',timeout=15)
 passed=all(tls['checks'].get(n) for n in ['TLSv1_2_exact_65536','TLSv1_3_exact_65536','TLSv1_2_upload_digest_exact','TLSv1_3_upload_digest_exact']) and final['exit_code']==0
 result={'status':'PASS_ETH0_TLS_BIDIRECTIONAL_AND_PINNED_SSH' if passed else 'ETH0_GATES_INCOMPLETE','tls_checks':tls['checks'],'final':final,'flash':False,'bootenv':False,'automatic_eth1_return_pending':True}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
