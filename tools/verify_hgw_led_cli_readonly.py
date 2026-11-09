"""Run only list/status of the immutable LED candidate on pinned HGW ash."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
CANDIDATE=ROOT/'outputs/rea/arc700-20261021-r2/led-cli-candidate-r2-20261021T215300Z/om-ledctl'
PIN='0b2509b8dbd628174b952d6b115c6e6be3a39f89b96514e2f17290fae5e81753'
BOOT='5f513265-a294-4366-9567-e1d8af704b6b'
KNOWN=DEVICE/'firmware/f367r9-f365-transition-observation-device-bound/known_hosts.f367'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert sha(CANDIDATE)==PIN
    now=datetime.now(timezone.utc)
    out=ROOT/'outputs/rea/arc700-20261021-r2'/('led-cli-target-readonly-'+now.strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    known=sha(KNOWN)
    base=[str(Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'),'-i',str(Path.home()/'.ssh/id_ed25519'),'-b','192.168.1.49',
        '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(KNOWN),'-o','LogLevel=ERROR','root@192.168.1.90']
    checks=[]
    for mode in ('list','status'):
        command="test \"$(cat /proc/sys/kernel/random/boot_id)\" = '"+BOOT+"' && /bin/ash -s -- "+mode
        proc=subprocess.run(base+[command],input=CANDIDATE.read_bytes(),capture_output=True,timeout=20)
        text=proc.stdout.decode('utf-8','replace')
        assert not re.search(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}',text)
        (out/(mode+'.stdout')).write_text(text,encoding='utf-8')
        (out/(mode+'.stderr')).write_bytes(proc.stderr)
        check={'mode':mode,'exit_code':proc.returncode,'stderr_empty':not proc.stderr}
        if mode=='status' and proc.returncode==0:
            data=json.loads(text)
            check['cached_request_explicit']=data['readback_kind']=='led-class-cached-request'
            check['stage0_gpio_correct']=data['stage0']['gpio']==9
            check['gpio9_alias_consistent']=data['gpio9_alias_consistent']
            check['lower_requests_off']=all(data['channels'][n]['brightness']=='0' for n in ('signalb','signalg','signalr'))
        if mode=='list' and proc.returncode==0:
            rows=text.splitlines()
            check['six_devices_listed']=len(rows)==7
            check['stage0_correct_path']=any(line.startswith('stage0\t9\t/sys/class/leds/topaz:stage0:alive/brightness\t') for line in rows)
        checks.append(check)
    passed=all(c['exit_code']==0 and c['stderr_empty'] and all(v is True for k,v in c.items() if k not in ('mode','exit_code','stderr_empty')) for c in checks)
    result={'status':'PASS_TARGET_ASH_READONLY_QUERIES' if passed else 'FAIL_TARGET_ASH_READONLY_QUERIES',
        'checks':checks,'candidate_sha256':PIN,'known_hosts_unchanged':known==sha(KNOWN),
        'expected_boot':BOOT,'read_only':True,'installed':False,'led_writes':False,
        'identify_executed':False,'physical_colour_verified':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps({'directory':str(out),**result}))
    return int(not passed)

if __name__=='__main__':raise SystemExit(main())
