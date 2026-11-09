"""Preserve a fresh redacted read-only baseline before offline R2 integration."""
from pathlib import Path
from datetime import datetime,timezone
import json
from ssh_radio73 import execute,ROOT
COMMAND=r'''uname -r
cat /proc/uptime
/usr/sbin/hostapd_cli -p /run/hostapd status | /bin/busybox grep -E 'state=|country_code=|channel=|num_sta\[0\]='
cat /sys/class/net/eth0/carrier
cat /sys/class/net/eth1/operstate
cat /proc/net/dev
head -n 3 /proc/meminfo
/bin/busybox dmesg -s 16384 | /bin/busybox grep -E 'Kernel panic|Oops:|BUG:|Fatal exception|quiesce.*timeout|DMA.*timeout' | /bin/busybox sed -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/REDACTED/g'
'''
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 out=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z'/('radio73-r2-baseline-'+stamp)
 out.mkdir()
 result=execute(COMMAND,host='192.168.1.90',timeout=15)
 result.update(utc=datetime.now(timezone.utc).isoformat(),operation='read-only current radio73 baseline',hardware_mutations=False,flash_writes=0,bootenv_writes=0)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
