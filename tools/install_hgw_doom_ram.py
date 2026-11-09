"""Install authorized same-origin Doom and LED CLI in RAM; no flash/reboot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BOOT='5f513265-a294-4366-9567-e1d8af704b6b'
BASE='/run/openmitrastar/doom-20261022-r1'
FILES=BASE+'/files'
HELPER=ROOT/'outputs/doom/ram-mount-20261022-r5-nolibc/hgw-doom-ram-mount-a'
HELPER_SHA='3ed845185777299ca2f2798daa31c2d0d932502e1afdde6341c4c8fb745181b5'
LED=ROOT/'outputs/rea/arc700-20261021-r2/led-cli-candidate-r2-20261021T215300Z/om-ledctl'
LED_SHA='0b2509b8dbd628174b952d6b115c6e6be3a39f89b96514e2f17290fae5e81753'
KNOWN=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f367r9-f365-transition-observation-device-bound/known_hosts.f367'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--web',type=Path);parser.add_argument('--stage-only',action='store_true');parser.add_argument('--resume-stage',action='store_true');parser.add_argument('--publish-existing',action='store_true');args=parser.parse_args()
    assert sha(HELPER)==HELPER_SHA and sha(LED)==LED_SHA
    now=datetime.now(timezone.utc);out=ROOT/'outputs/doom'/('ram-install-'+now.strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(exist_ok=False)
    argv=[str(Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'),'-i',str(Path.home()/'.ssh/id_ed25519'),'-b','192.168.1.49',
        '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(KNOWN),'-o','LogLevel=ERROR','root@192.168.1.90']
    events=[];guard="test \"$(cat /proc/sys/kernel/random/boot_id)\" = '"+BOOT+"' && "
    def run(name,command,data=None,timeout=30):
        proc=subprocess.run(argv+[guard+command],input=data,capture_output=True,timeout=timeout)
        stdout=proc.stdout.decode('utf-8','replace');stderr=proc.stderr.decode('utf-8','replace')
        mac=re.compile(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}')
        stdout=mac.sub('[IDENTITY-REDACTED]',stdout);stderr=mac.sub('[IDENTITY-REDACTED]',stderr)
        events.append({'stage':name,'exit_code':proc.returncode,'stdout':stdout,'stderr':stderr})
        (out/(name+'.stdout')).write_text(stdout,encoding='utf-8');(out/(name+'.stderr')).write_text(stderr,encoding='utf-8')
        print(json.dumps({'stage':name,'exit_code':proc.returncode,'stdout':stdout}),flush=True)
        if proc.returncode:raise RuntimeError(name+' failed')
        return stdout
    def upload(path,target):
        assert re.fullmatch('/run/openmitrastar/doom-20261022-r1/[A-Za-z0-9_./-]+',target) and '..' not in target.split('/')
        run('upload-'+str(len(events)),"umask 022; test ! -e '"+target+"' && cat > '"+target+"'",path.read_bytes(),60)
        actual=run('hash-'+str(len(events)),"sha256sum '"+target+"' | awk '{print $1}'").strip()
        assert actual==sha(path)
    web_bound=False;led_bound=False
    http_restarted=False
    def restart_http(name):
        run(name,"sh -s",b'''set -eu
p=$(cat /run/openmitrastar/web/mini_httpd.pid)
case "$p" in ''|*[!0-9]*) exit 41;; esac
test "$(cat /proc/$p/comm)" = mini_httpd
kill "$p"
n=0
while kill -0 "$p" 2>/dev/null;do n=$((n+1));test "$n" -lt 8;sleep 1;done
/usr/sbin/mini_httpd -u root -C /etc/minihttpd-oem.conf
n=0
while :;do
 p=$(cat /run/openmitrastar/web/mini_httpd.pid 2>/dev/null || true)
 case "$p" in ''|*[!0-9]*) ;; *) if kill -0 "$p" 2>/dev/null;then echo HTTP_RESTART_PASS;break;fi;; esac
 n=$((n+1));test "$n" -lt 8;sleep 1
done
''',20)
    try:
        if args.stage_only:
            if args.resume_stage:
                run('admission',"test -d '"+BASE+"' && test ! -e '"+FILES+"' && test ! -e '"+BASE+"/mount-helper-nolibc'")
            else:
                run('admission',"test ! -e '"+BASE+"' && mkdir '"+BASE+"'")
            upload(HELPER,BASE+'/mount-helper-nolibc')
            run('helper-executable',"chmod 700 '"+BASE+"/mount-helper-nolibc'")
            run('space-inspect',BASE+'/mount-helper-nolibc inspect')
            run('stage-ram-web',BASE+'/mount-helper-nolibc stage')
            run('mkdir-web',"mkdir '"+FILES+"/www'")
            producer=subprocess.Popen(argv+[guard+'tar -cf - -C /www .'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            consumer=subprocess.run(argv+[guard+"tar -xf - -C '"+FILES+"/www'"],stdin=producer.stdout,capture_output=True,timeout=30)
            producer.stdout.close();producer.wait(timeout=30)
            assert producer.returncode==0 and consumer.returncode==0 and not producer.stderr.read() and not consumer.stderr
            run('copied-home-hashes',"sha256sum /www/index.html '"+FILES+"/www/index.html' /www/app.js '"+FILES+"/www/app.js'")
            status='PASS_RAM_WEB_STAGE_ONLY'
        else:
            assert args.web and args.web.is_dir()
            paths=sorted(p for p in args.web.rglob('*') if p.is_file())
            assert paths and sum(p.stat().st_size for p in paths)<=6300000
            absence='' if args.publish_existing else " && test ! -e '"+FILES+"/www/Doom'"
            run('existing-stage',"test -d '"+FILES+"/www'"+absence+" && test \"$(sha256sum '"+BASE+"/mount-helper-nolibc' | awk '{print $1}')\" = '"+HELPER_SHA+"'")
            for p in paths:
                rel=p.relative_to(args.web).as_posix()
                assert re.fullmatch('[A-Za-z0-9_./-]+',rel) and '..' not in rel.split('/') and rel.startswith('Doom/')
                target=FILES+'/www/'+rel
                if args.publish_existing:
                    if rel=='Doom/index.html':
                        upload(p,target+'.r2')
                        run('activate-r2-index',"mv '"+target+".r2' '"+target+"'")
                    else:
                        actual=run('reused-hash-'+str(len(events)),"sha256sum '"+target+"' | awk '{print $1}'").strip();assert actual==sha(p)
                else:
                    parent=rel.rsplit('/',1)[0]
                    run('mkdir-'+str(len(events)),"mkdir -p '"+FILES+'/www/'+parent+"'")
                    upload(p,target)
            if not args.publish_existing:
                upload(LED,FILES+'/om-ledctl');run('led-executable',"chmod 755 '"+FILES+"/om-ledctl'")
            else:
                run('reused-led-hash',"test \"$(sha256sum '"+FILES+"/om-ledctl' | awk '{print $1}')\" = '"+LED_SHA+"'")
            run('expose-web',BASE+'/mount-helper-nolibc expose');web_bound=True
            run('install-led',BASE+'/mount-helper-nolibc led');led_bound=True
            run('led-readback',"test \"$(sha256sum /usr/sbin/om-ledctl | awk '{print $1}')\" = '"+LED_SHA+"' && /usr/sbin/om-ledctl status")
            restart_http('restart-http-for-new-root');http_restarted=True
            for p in paths:
                rel=p.relative_to(args.web).as_posix();body=urllib.request.urlopen('http://192.168.1.90/'+rel,timeout=20).read()
                assert hashlib.sha256(body).hexdigest()==sha(p)
            controls=run('preserved-controls',"/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | sed -n 's/^state=//p'; /usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping; cat /sys/module/qdrv/parameters/openmitrastar_rf_enable; cat /sys/class/watchdog/watchdog0/f340_control")
            assert controls.splitlines()==['ENABLED','PONG','1','00000000']
            status='PASS_DOOM_HTTP_ASSETS_AND_LED_RAM_INSTALLED'
    except Exception as error:
        status='FAILED_'+type(error).__name__
        if led_bound:run('rollback-led',BASE+'/mount-helper-nolibc unled')
        if web_bound:run('rollback-web',BASE+'/mount-helper-nolibc unweb')
        if http_restarted:restart_http('rollback-http-original-root')
        raise
    finally:
        result={'status':locals().get('status','FAILED'),'boot':BOOT,'events':events,'flash_writes':False,'reboot':False,'persistent':False,'web_bound':web_bound,'led_bound':led_bound,'http_restarted':http_restarted,'boot_timing_installed':False,'gameplay_verified':False}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'result':str(out/'result.json'),'status':result['status']}),flush=True)

if __name__=='__main__':main()
