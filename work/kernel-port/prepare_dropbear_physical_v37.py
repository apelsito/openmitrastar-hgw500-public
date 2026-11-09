"""Launch qualified key-only build with options actually compiled in2026.94."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-dropbear-pie-v36'
NEW=ROOT/'work/kernel-port/linux-7.3-dropbear-pie-v37'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 scripts={'runtime':'uname -r','pin':'sha256sum /run/dropbear73-pie','version':'/run/dropbear73-pie dropbear -V; echo SSH_VERSION_RC=$?',
 'launch':'/run/dropbear73-pie dropbear -F -j -k -r /etc/dropbear/dropbear_ed25519_host_key -p 22 -P /run/dropbear73-pie.pid >/run/dropbear73.log 2>&1 & echo SSH_LAUNCH_PID=$!; sleep 1; cat /run/dropbear73-pie.pid',
 'after':'ps; cat /run/dropbear73.log; cat /proc/uptime'}
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R36-'+self.nonce[:8]+'-'+name","marker='R37-'+self.nonce[:8]+'-'+name")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V37_CORRECT_CURRENT_DROPBEAR_FLAGS_READY')
if __name__=='__main__':main()
