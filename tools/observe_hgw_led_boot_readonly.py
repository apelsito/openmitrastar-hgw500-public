"""Read-only pinned SSH evidence for HGW LEDs/boot; never probes raw GPIO."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
KNOWN = DEVICE/'firmware/f367r9-f365-transition-observation-device-bound/known_hosts.f367'
EXPECTED_BOOT = '5f513265-a294-4366-9567-e1d8af704b6b'
SCRIPT = r'''set -eu
test "$(cat /proc/sys/kernel/random/boot_id)" = '5f513265-a294-4366-9567-e1d8af704b6b'
echo HGW_LED_BOOT_BEGIN
printf 'boot=';cat /proc/sys/kernel/random/boot_id
printf 'kernel=';uname -r
printf 'version=';sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'ready=';cat /run/openmitrastar/boot-state
printf 'uptime=';cut -d' ' -f1 /proc/uptime
for name in openmitrastar:green:wlan2g openmitrastar:green:wlan5g openmitrastar:panel:signalb openmitrastar:panel:signalg openmitrastar:panel:signalr topaz:stage0:alive;do
 p=/sys/class/leds/$name
 if [ -d "$p" ];then
  printf 'led.%s.brightness=' "$name";cat "$p/brightness"
  printf 'led.%s.max=' "$name";cat "$p/max_brightness"
  printf 'led.%s.trigger=' "$name";cat "$p/trigger" 2>/dev/null || echo absent
 else printf 'led.%s=absent\n' "$name";fi
done
for file in /etc/init.d/S90-ready /usr/sbin/om-ledctl /usr/share/openmitrastar/leds/hgw500-leds.json;do
 printf 'hash.%s=' "$file";sha256sum "$file" 2>/dev/null | awk '{print $1}'
done
echo READY_LED_WRITERS_BEGIN
grep -in 'led' /etc/init.d/S90-ready || true
echo READY_LED_WRITERS_END
printf 'radio2=';/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | sed -n 's/^state=//p'
printf 'radio5=';/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping
printf 'rf=';cat /sys/module/qdrv/parameters/openmitrastar_rf_enable
printf 'watchdog=';cat /sys/class/watchdog/watchdog0/f340_control
printf 'fatal=';dmesg | grep -Eic 'MuC.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|QMAC.*fatal|DMA.*fatal|thermal.*fatal' || true
echo LED_DMESG_BEGIN
dmesg | grep -Ei 'stage0 alive LED|wlan.*LED|panel.*LED|recovery.*LED' | tail -n 20 || true
echo LED_DMESG_END
echo BOOT_PROFILE_BEGIN
for file in /etc/init.d/rcS /etc/init.d/S35-radio-modules /etc/init.d/S50-radio-ap /usr/sbin/om-stage0-ready;do
 printf 'hash.%s=' "$file";sha256sum "$file" 2>/dev/null | awk '{print $1}'
done
logread 2>/dev/null | grep -E 'OMINIT_(START|END|SERVICE_START|SERVICE_END|FATAL)|OMPRODUCT_READY' | tail -n 60 || true
echo BOOT_PROFILE_END
echo HGW_LED_BOOT_END
'''

def main():
    now = datetime.now(timezone.utc)
    out = ROOT/'outputs/rea/arc700-20261021-r2'/('led-boot-readonly-'+now.strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    payload = SCRIPT.replace('\r\n', '\n').encode('ascii')
    (out/'probe.sh').write_bytes(payload)
    known_before = hashlib.sha256(KNOWN.read_bytes()).hexdigest()
    argv = [str(Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'),
        '-i',str(Path.home()/'.ssh/id_ed25519'),'-b','192.168.1.49',
        '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=5',
        '-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2',
        '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(KNOWN),
        '-o','LogLevel=ERROR','root@192.168.1.90','sh -s']
    proc = subprocess.run(argv,input=payload,capture_output=True,timeout=30)
    mac = re.compile(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}')
    stdout = mac.sub('[IDENTITY-REDACTED]',proc.stdout.decode('utf-8','replace'))
    stderr = mac.sub('[IDENTITY-REDACTED]',proc.stderr.decode('utf-8','replace'))
    (out/'stdout.txt').write_text(stdout,encoding='utf-8')
    (out/'stderr.txt').write_text(stderr,encoding='utf-8')
    result = {'observed_utc':now.isoformat(),'exit_code':proc.returncode,
        'complete_transcript':stdout.startswith('HGW_LED_BOOT_BEGIN\n') and stdout.rstrip().endswith('HGW_LED_BOOT_END'),
        'expected_boot':EXPECTED_BOOT,'read_only':True,'raw_gpio_read':False,
        'known_hosts_unchanged':hashlib.sha256(KNOWN.read_bytes()).hexdigest()==known_before,
        'probe_sha256':hashlib.sha256(payload).hexdigest()}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'directory':str(out),**result}))
    print(stdout)
    if stderr: print(stderr)
    return proc.returncode

if __name__=='__main__':raise SystemExit(main())
