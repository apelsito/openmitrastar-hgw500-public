"""Use fixed uhttpd config interpreter paths for extensionless LYOKO API."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'work/kernel-port/linux-7.3-radioeth-api-v26'
NEW=ROOT/'work/kernel-port/linux-7.3-radioeth-api-v27'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if NEW.exists():raise RuntimeError('Version exists')
 NEW.mkdir()
 names=['status','capabilities','storage','network','firmware','session','hardware-led-test','frontend','ssh','clients','privacy','packages','hardware','diagnostics']
 scripts={'runtime':'uname -r','cfg_init':': > /run/om73-web.conf'}
 for i,name in enumerate(names):scripts['c'+str(i)]="printf '%s\\n' '*/api/v1/"+name+":/bin/sh' >> /run/om73-web.conf"
 args='/usr/sbin/uhttpd -f -c /run/om73-web.conf -s 0.0.0.0:443 -h /www -C /etc/lyoko/tls/server.pem -K /etc/lyoko/tls/server.key -D -S -I index.cgi -x /api/v1 -i .cgi=/bin/sh -n 2 -N 8 -t 15 -T 20'
 scripts['args_init']=': > /run/om73-webargs'
 for i in range(0,len(args),80):scripts['a'+str(i//80)]="printf %s '"+args[i:i+80]+"' >> /run/om73-webargs"
 scripts['launch']='p=$(/bin/busybox pidof uhttpd); test -n "$p" && kill -TERM $p; sleep 1; /bin/busybox sh -c "$(cat /run/om73-webargs)" >/run/uhttpd-api.log 2>&1 & echo HTTPS_API_PID=$!; sleep 1; /bin/busybox pidof uhttpd'
 scripts['after']='cat /proc/uptime; cat /run/uhttpd-api.log'
 code=(OLD/'executor.py').read_text();a=code.index('SCRIPTS=');b=code.index('\n\nclass Flow',a)
 code=code[:a]+'SCRIPTS='+repr(scripts)+code[b:]
 code=code.replace("marker='R26-'+self.nonce[:8]+'-'+name","marker='R27-'+self.nonce[:8]+'-'+name")
 (NEW/'executor.py').write_text(code)
 for n in ['run.ps1','test_executor.py']:(NEW/n).write_bytes((OLD/n).read_bytes())
 pins=json.loads((OLD/'SOURCE_PINS.json').read_text())
 for p in [Path(__file__),NEW/'executor.py',NEW/'run.ps1',NEW/'test_executor.py']:pins[p.relative_to(ROOT).as_posix()]=sha(p)
 (NEW/'SOURCE_PINS.json').write_text(json.dumps(pins,indent=2)+'\n');print('V27_API_CONFIG_INTERPRETERS_READY')
if __name__=='__main__':main()
