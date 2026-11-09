"""Test exact corrected PIE executable and start modern pinned SSH in RAM."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-control-v23'
NEW=ROOT/'work/kernel-port/linux-7.3-dropbear-pie-v36'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 scripts={'runtime':'uname -r','pin':'sha256sum /run/dropbear73-pie','version':'/bin/busybox timeout -s KILL 4 /run/dropbear73-pie dropbear -V; echo SSH_VERSION_RC=$?',
 'launch':'/run/dropbear73-pie dropbear -E -s -r /etc/dropbear/dropbear_ed25519_host_key -p 22 -P /run/dropbear73-pie.pid >/run/dropbear73.log 2>&1; echo SSH_START_RC=$?; sleep 1; cat /run/dropbear73-pie.pid',
 'after':'ps; cat /run/dropbear73.log; cat /proc/uptime'}
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R23-'+self.nonce[:8]+'-'+name","marker='R36-'+self.nonce[:8]+'-'+name")
 code=code.replace("   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')","   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')\n   if name=='pin':m.BASE.require('23026d9cabd53cab1d9b7c5a78ef5c5be0e6842b7a81a1696af9949bf5974da0' in gates[name],'Corrected SSH executable drift')\n   if name=='version':m.BASE.require('SSH_VERSION_RC=0' in gates[name],'Dropbear corrected version still fails')")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V36_CORRECTED_DROPBEAR_PHYSICAL_READY')
if __name__=='__main__':main()
