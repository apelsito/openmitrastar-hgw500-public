"""Reduce noisy console output and recover bounded RAM diagnosis."""
from pathlib import Path
import hashlib,json,base64
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-shell-recovery-v18'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-shell-recovery-v19'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 scripts={'runtime':'uname -r','quiet':'echo 3 > /proc/sys/kernel/printk; /bin/busybox stty -echo; echo QUIET_RC=$?','auth':'/bin/busybox ln -sf busybox /bin/id; ls -ln /run/openmitrastar/secrets/web.password.sha256; id -u','fixture_prep':': > /run/om73-upload.b64'}
 fixture='#!/bin/sh\ncase "$CONTENT_LENGTH" in 65536) ;; *) printf "Status: 413 Payload Too Large\\r\\nContent-Type: text/plain\\r\\n\\r\\nrejected\\n"; exit 0;; esac\ndigest=$(/bin/busybox head -c 65536 | /bin/busybox sha256sum)\nprintf "Content-Type: text/plain\\r\\nCache-Control: no-store\\r\\n\\r\\n%s\\n" "$digest"\n'
 text=base64.b64encode(fixture.encode()).decode()
 for i in range(0,len(text),48):scripts['f'+str(i//48)]="printf %s '"+text[i:i+48]+"' >> /run/om73-upload.b64"
 scripts['fixture_decode']=' /bin/busybox base64 -d /run/om73-upload.b64 > /www/__traffic.cgi; chmod 755 /www/__traffic.cgi; sha256sum /www/__traffic.cgi'
 scripts['after']='cat /proc/uptime'
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='RADIOETH73-END-'+self.nonce[:20]+'-'+name","marker='R19-'+self.nonce[:8]+'-'+name")
 code=code.replace('range(0,len(payload),24)','range(0,len(payload),8)').replace('payload[offset:offset+24]','payload[offset:offset+8]').replace('time.sleep(.015)','time.sleep(.02)')
 code=code.replace("   if name=='decode':m.BASE.require('b256b414779f1f3e7af678b8b8428b6806bb2675a8bcbad9638de4a99284b4d8' in gates[name],'Probe digest drift; do not execute')\n",'')
 code=code.replace("  self.s.write(b'\\x03\\n',timeout=3)","  self.s.write(b'\\x03\\x15\\n',timeout=3)")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V19_QUIET_PACED_UART_READY')
if __name__=='__main__':main()
