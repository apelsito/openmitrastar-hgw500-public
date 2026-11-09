"""Read current WPA2 authorization/counters during exact AELITA client gate."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-observe-v6'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-station-v22'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 query="/usr/sbin/hostapd_cli -p /run/hostapd all_sta | /bin/busybox grep -E 'flags=|rx_bytes=|tx_bytes=|rx_packets=|tx_packets=|auth_alg=|wpa='"
 scripts={'runtime':'uname -r','s0':query,'s1':'sleep 2; '+query,'s2':'sleep 2; '+query,'stats':'cat /proc/net/dev; cat /proc/interrupts','s3':'sleep 2; '+query}
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS={');b=code.index('\n}\n',a)+2
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='RADIOETH73-END-'+self.nonce[:20]+'-'+name","marker='R22-'+self.nonce[:8]+'-'+name")
 code=code.replace("  self.safe();self.fresh();self.s.write((script+\"; printf '\\\\n\"+marker+\"\\\\n'\\n\").encode(),timeout=3)","  self.safe();self.fresh()\n  payload=(script+\"; printf '\\\\n\"+marker+\"\\\\n'\\n\").encode()\n  for offset in range(0,len(payload),8):\n   self.safe();self.s.write(payload[offset:offset+8],timeout=3);time.sleep(.02)")
 assert 'for offset in range' in code
 code=code.replace("'PASS_CURRENT_RAM_DIAGNOSTIC'","'PASS_REDACTED_STATION_OBSERVATION'")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V22_STATION_READONLY_READY')
if __name__=='__main__':main()
