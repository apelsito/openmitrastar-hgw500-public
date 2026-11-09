"""Short quiet UART diagnosis after finite WiFi TLS traffic, no credentials."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-station-v22'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-control-v23'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 scripts={
  'runtime':'uname -r; cat /proc/uptime; cat /proc/meminfo | head -n 5',
  'authlog':"/bin/busybox grep -E 'AP-STA-CONNECTED|AP-STA-DISCONNECTED|authorized|associated|authenticated' /run/hostapd-private.log | /bin/busybox sed -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/CLIENT/g' | tail -n 10",
  'webshape':'ls -ln /run/openmitrastar/secrets/web.password.sha256; id -u; head -n 1 /run/openmitrastar/secrets/web.password.sha256 | wc -c',
  'webvalid':"/bin/busybox sh -c 'head -n 1 /run/openmitrastar/secrets/web.password.sha256 | grep -Eq \"^[0-9a-f]{64}$\"; echo HASH_VALID_RC=$?'",
  'apps':'ls -l /bin/id /bin/head /bin/grep /bin/awk /bin/sha256sum; /bin/busybox stty -a',
  'radio':'/usr/sbin/hostapd_cli -p /run/hostapd status | grep -E "state=|num_sta|channel=|country_code="; cat /proc/net/dev',
 }
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R22-'+self.nonce[:8]+'-'+name","marker='R23-'+self.nonce[:8]+'-'+name")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V23_SHORT_CONTROL_READY')
if __name__=='__main__':main()
