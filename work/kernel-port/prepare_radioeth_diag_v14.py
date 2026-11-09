"""Prepare finite RAM diagnostics and TLS upload fixture; no hardware action."""
from pathlib import Path
import subprocess,hashlib,json,base64
ROOT=Path(__file__).resolve().parents[2]
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-diagnostic-v14'
PARENT=ROOT/'work/kernel-port/linux-7.3-radioeth-observe-v6'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Immutable output exists')
 NEW.mkdir()
 binary=subprocess.run(['wsl.exe','-d','REA-Linux','-u','root','--','python3','-c',"import pathlib,sys;sys.stdout.buffer.write(pathlib.Path('/home/rea/openmitrastar-linux73-20261022T135100Z/dropbear73-signal-probe-qualified-v2/probe').read_bytes())"],capture_output=True,check=True).stdout
 assert hashlib.sha256(binary).hexdigest()=='5c98e16408c5fd2b97a45ebf568d1b284adb4746f081d52a45df4a22b348422e'
 (NEW/'signal-probe').write_bytes(binary)
 scripts={
  'runtime':'uname -r; cat /proc/uptime; ps; cat /proc/sys/kernel/tainted',
  'tls_events':"for p in $(/bin/busybox pidof uhttpd); do echo TLS_PROCESS; cat /proc/$p/stat /proc/$p/wchan /proc/$p/syscall; /bin/busybox ls -l /proc/$p/fd; done",
  'radio_auth':"/bin/busybox timeout -s KILL 4 /usr/sbin/hostapd_cli -p /run/hostapd all_sta; echo STATION_QUERY_RC=$?; /bin/busybox grep -c AP-STA-CONNECTED /run/hostapd-private.log; /bin/busybox grep -c AP-STA-DISCONNECTED /run/hostapd-private.log",
  'fault_tail':"/bin/busybox dmesg -s 4096 | /bin/busybox tail -n 22",
 }
 text=base64.b64encode(binary).decode()
 scripts['probe_begin']="test ! -e /run/om73-signal-probe && : > /run/om73-signal-probe.b64; echo PROBE_INIT_RC=$?"
 for i in range(0,len(text),160):scripts['probe_chunk_'+str(i//160)]= "printf '%s' '"+text[i:i+160]+"' >> /run/om73-signal-probe.b64"
 scripts['probe_decode']="/bin/busybox base64 -d /run/om73-signal-probe.b64 > /run/om73-signal-probe; /bin/busybox chmod 700 /run/om73-signal-probe; /bin/busybox sha256sum /run/om73-signal-probe; /bin/busybox rm /run/om73-signal-probe.b64"
 scripts['probe_run']="/bin/busybox timeout -s KILL 6 /run/om73-signal-probe; echo PROBE_RC=$?"
 fixture='#!/bin/sh\ncase "$CONTENT_LENGTH" in 65536) ;; *) printf "Status: 413 Payload Too Large\\r\\nContent-Type: text/plain\\r\\n\\r\\nrejected\\n"; exit 0;; esac\ndigest=$(/bin/busybox head -c 65536 | /bin/busybox sha256sum)\nprintf "Content-Type: text/plain\\r\\nCache-Control: no-store\\r\\n\\r\\n%s\\n" "$digest"\n'
 encoded=base64.b64encode(fixture.encode()).decode()
 scripts['upload_fixture']="printf '%s' '"+encoded+"' | /bin/busybox base64 -d > /www/__traffic.cgi; /bin/busybox chmod 755 /www/__traffic.cgi; /bin/busybox sha256sum /www/__traffic.cgi"
 scripts['final_runtime']='ps; cat /proc/uptime'
 code=(PARENT/'executor.py').read_text()
 start=code.index('SCRIPTS={');end=code.index('\n}\n',start)+2
 code=code[:start]+'SCRIPTS='+repr(scripts)+code[end:]
 code=code.replace("  status=self.synchronize_nonce(m.KERNEL);gates={'kernel':parent.safe_text(status)}", "  prior=json.loads((ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/radioeth73-events-physical-powercycle-v12/result.json').read_text())\n  m.BASE.require(prior['artifact']['sha256']==self.config['sha256'] and prior['bootm']==1 and prior['flash_writes']==prior['bootenv_writes']==0,'Exact new RAM boot absent')\n  status=self.synchronize_nonce(m.KERNEL);gates={'kernel':parent.safe_text(status)}")
 code=code.replace("'PASS_CURRENT_RAM_DIAGNOSTIC'","'PASS_EVENTS_RAM_DIAGNOSTIC_WITH_PROBE_AND_UPLOAD_FIXTURE'")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((PARENT/n).read_bytes())
 pins=json.loads((PARENT/'SOURCE_PINS.json').read_text())
 for p in [NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py',NEW/'signal-probe',Path(__file__),ROOT/'work/kernel-port/dropbear73-signal-probe-v1/probe.c']:
  pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
 print(json.dumps({'status':'RAM_DIAGNOSTIC_EXECUTOR_PREPARED','probe_bytes':len(binary),'probe_sha256':hashlib.sha256(binary).hexdigest(),'upload_fixture_sha256':hashlib.sha256(fixture.encode()).hexdigest(),'flash_writes':0,'bootenv_writes':0}))
if __name__=='__main__':main()
