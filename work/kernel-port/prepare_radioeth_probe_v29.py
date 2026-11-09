"""Stage the exact EXITKILL signal probe over recovered quiet UART."""
from pathlib import Path
import base64,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-control-v23'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-probe-v29'
PROBE=ROOT/'work/kernel-port/linux-7.3-radioeth-diagnostic-v17/signal-probe'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 assert sha(PROBE)=='b256b414779f1f3e7af678b8b8428b6806bb2675a8bcbad9638de4a99284b4d8'
 text=base64.b64encode(PROBE.read_bytes()).decode()
 scripts={'runtime':'uname -r','init':': > /run/om73-probe.b64'}
 for i in range(0,len(text),64):scripts['p'+str(i//64)]="printf %s '"+text[i:i+64]+"' >> /run/om73-probe.b64"
 scripts['decode']=' /bin/busybox base64 -d /run/om73-probe.b64 > /run/om73-signal-probe; chmod 700 /run/om73-signal-probe; sha256sum /run/om73-signal-probe'
 scripts['signal']=' /bin/busybox timeout -s KILL 6 /run/om73-signal-probe; echo PROBE_RC=$?'
 scripts['after']='cat /proc/uptime; ps'
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R23-'+self.nonce[:8]+'-'+name","marker='R29-'+self.nonce[:8]+'-'+name")
 code=code.replace("   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')","   gates[name]=self.shell_script(name);(self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')\n   if name=='decode':m.BASE.require('b256b414779f1f3e7af678b8b8428b6806bb2675a8bcbad9638de4a99284b4d8' in gates[name],'Probe hash mismatch; do not execute')")
 assert 'Probe hash mismatch' in code
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),PROBE,NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V29_QUIET_SIGNAL_PROBE_READY')
if __name__=='__main__':main()
