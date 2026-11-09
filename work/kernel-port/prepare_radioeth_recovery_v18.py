"""Recover interrupted current shell and stage exact bounded diagnostics slowly."""
from pathlib import Path
import base64,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-shell-recover-v7'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-shell-recovery-v18'
PROBE=ROOT/'work/kernel-port/linux-7.3-radioeth-diagnostic-v17/signal-probe'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 probe=PROBE.read_bytes();assert sha(PROBE)=='b256b414779f1f3e7af678b8b8428b6806bb2675a8bcbad9638de4a99284b4d8'
 scripts={'runtime':'uname -r; cat /proc/uptime; ps','prep':'stty -echo 2>/dev/null; /bin/busybox ln -sf busybox /bin/id; /bin/busybox rm -f /run/om73-signal-probe.b64; : > /run/om73-signal-probe.b64'}
 text=base64.b64encode(probe).decode()
 for i in range(0,len(text),64):scripts['probe_part_'+str(i//64)]="printf '%s' '"+text[i:i+64]+"' >> /run/om73-signal-probe.b64"
 scripts['decode']=' /bin/busybox base64 -d /run/om73-signal-probe.b64 > /run/om73-signal-probe; chmod 700 /run/om73-signal-probe; sha256sum /run/om73-signal-probe'
 scripts['signal']=' /bin/busybox timeout -s KILL 6 /run/om73-signal-probe; echo PROBE_RC=$?'
 scripts['auth_shape']='test -f /run/openmitrastar/secrets/web.password.sha256; echo HASH_EXISTS=$?; ls -ln /run/openmitrastar/secrets/web.password.sha256; id -u'
 fixture='#!/bin/sh\ncase "$CONTENT_LENGTH" in 65536) ;; *) printf "Status: 413 Payload Too Large\\r\\nContent-Type: text/plain\\r\\n\\r\\nrejected\\n"; exit 0;; esac\ndigest=$(/bin/busybox head -c 65536 | /bin/busybox sha256sum)\nprintf "Content-Type: text/plain\\r\\nCache-Control: no-store\\r\\n\\r\\n%s\\n" "$digest"\n'
 text=base64.b64encode(fixture.encode()).decode();scripts['fixture_prep']=': > /run/om73-upload.b64'
 for i in range(0,len(text),64):scripts['fixture_part_'+str(i//64)]="printf '%s' '"+text[i:i+64]+"' >> /run/om73-upload.b64"
 scripts['fixture_decode']=' /bin/busybox base64 -d /run/om73-upload.b64 > /www/__traffic.cgi; chmod 755 /www/__traffic.cgi; sha256sum /www/__traffic.cgi'
 scripts['last']='ps; cat /proc/uptime'
 code=(OLD/'executor.py').read_text()
 begin=code.index('SCRIPTS={');end=code.index('\n}\n',begin)+2
 code=code[:begin]+'SCRIPTS='+repr(scripts)+code[end:]
 start=code.index('  for name in [\'runtime\',\'faults\']:');end=code.index("  self.fresh();self.s.write(b'exit",start)
 code=code[:start]+"  for name in SCRIPTS:\n   gates[name]=self.shell_script(name)\n   (self.output/'gates.json').write_text(json.dumps(gates,indent=2)+'\\n')\n   if name=='runtime':m.BASE.require(m.KERNEL.decode() in gates[name],'Current kernel differs')\n   if name=='decode':m.BASE.require('b256b414779f1f3e7af678b8b8428b6806bb2675a8bcbad9638de4a99284b4d8' in gates[name],'Probe digest drift; do not execute')\n   if name=='fixture_decode':m.BASE.require('3fe089928e1d2e90a3d8eddcebff12f24b81faeb1875dcd2841a4f0fe31fb3ae' in gates[name],'Upload fixture digest drift')\n"+code[end:]
 code=code.replace("  self.safe();self.fresh();self.s.write((script+\"; printf '\\\\n\"+marker+\"\\\\n'\\n\").encode(),timeout=3)","  self.safe();self.fresh()\n  payload=(script+\"; printf '\\\\n\"+marker+\"\\\\n'\\n\").encode()\n  for offset in range(0,len(payload),24):\n   self.safe();self.s.write(payload[offset:offset+24],timeout=3);time.sleep(.015)")
 assert 'for offset in range' in code
 (NEW/'executor.py').write_text(code)
 for name in ['run.ps1','test_executor.py']:(NEW/name).write_bytes((OLD/name).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),PROBE,NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 print('V18_PACED_SHELL_RECOVERY_READY')
if __name__=='__main__':main()
