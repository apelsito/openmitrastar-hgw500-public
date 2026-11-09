"""Finite redacted station observation while AELITA performs encrypted traffic."""
from pathlib import Path
import json,time
from ssh_radio73 import execute,ROOT
def main():
 output=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-authorized-station-v39'
 if output.exists():raise ValueError('Immutable evidence exists')
 output.mkdir()
 command="/usr/sbin/hostapd_cli -p /run/hostapd all_sta | /bin/busybox sed -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/CLIENT/g' | /bin/busybox grep -E 'flags=|rx_bytes=|tx_bytes=|rx_packets=|tx_packets=|auth_alg=|^wpa='; /bin/busybox cat /proc/net/dev | /bin/busybox grep wlan0"
 rows=[]
 for i in range(32):
  r=execute(command,timeout=12);rows.append({'sample':i,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**r})
  result={'status':'PASS_WPA2_AUTHORIZED_COUNTERS' if any('[AUTHORIZED]' in x['stdout'] for x in rows) else 'WAITING_AUTHORIZED_CLIENT','rows':rows,'flash':False,'radio_changed':False,'client_identity_redacted':True}
  (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
  if i%8==0:print(json.dumps({'sample':i,'authorized':any('[AUTHORIZED]' in x['stdout'] for x in rows)}),flush=True)
  time.sleep(2)
 print(json.dumps({'status':result['status'],'samples':len(rows)}))
if __name__=='__main__':main()
