"""Use explicit shell interpreters for extensionless fixed LYOKO API paths."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-webhash-v24'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-api-v26'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 names=['status','capabilities','storage','network','firmware','session','hardware-led-test','frontend','ssh','clients','privacy','packages','hardware','diagnostics']
 args="/usr/sbin/uhttpd -f -s 0.0.0.0:443 -h /www -C /etc/lyoko/tls/server.pem -K /etc/lyoko/tls/server.key -D -S -I index.cgi -x /api/v1 -i .cgi=/bin/sh -n 2 -N 8 -t 15 -T 20 "+' '.join('-i /api/v1/'+n+'=/bin/sh' for n in names)
 scripts={'runtime':'uname -r','args_init':': > /run/om73-webargs'}
 for i,part in enumerate(args.split(' -i ')):
  text=part if i==0 else ' -i '+part
  scripts['arg'+str(i)]="printf %s '"+text+"' >> /run/om73-webargs"
 scripts['web_restart']='p=$(/bin/busybox pidof uhttpd); test -n "$p" && kill -TERM $p; /bin/busybox sh -c "$(cat /run/om73-webargs)" >/run/uhttpd-api.log 2>&1 & echo HTTPS_RESTART_PID=$!; sleep 1; /bin/busybox pidof uhttpd'
 scripts['after']='cat /proc/uptime; cat /run/uhttpd-api.log'
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R24-'+self.nonce[:8]+'-'+name","marker='R26-'+self.nonce[:8]+'-'+name")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V26_EXPLICIT_API_INTERPRETERS_READY')
if __name__=='__main__':main()
