"""Capture fresh dual-radio control/management evidence through pinned SSH.

No runtime writes, active traffic, UART, client identities, credentials or
calibration payloads. Interface counters alone do not establish client traffic.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
KNOWN_HOSTS = Path.home() / '.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f367r9-f365-transition-observation-device-bound/known_hosts.f367'
MAC = re.compile(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}')
REMOTE = r'''echo OM_DUAL_BEGIN
printf 'boot_id=';cat /proc/sys/kernel/random/boot_id
printf 'kernel=';uname -r
printf 'version=';sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'uptime=';awk '{print $1}' /proc/uptime
printf 'memory_available_kb=';awk '/^MemAvailable:/{print $2}' /proc/meminfo
printf 'radio2_state=';/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | sed -n 's/^state=//p'
printf 'radio2_channel=';/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | sed -n 's/^channel=//p'
printf 'radio5_ping=';/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping
printf 'radio5_frequency=';/usr/sbin/iwconfig-qtn wifi0 2>/dev/null | sed -n 's/.*Frequency:\([0-9.]*\) GHz.*/\1/p'
printf 'radio5_rf=';cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null || echo absent
for radio in 2 5;do
 if [ "$radio" = 2 ];then sta=$(/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 all_sta 2>/dev/null);else sta=$(/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 all_sta 2>/dev/null);fi
 printf '%s\n' "$sta" | awk -v radio="$radio" '/^flags=/ {n++;if(index($0,"[AUTH]"))a++;if(index($0,"[ASSOC]"))s++;if(index($0,"[AUTHORIZED]"))z++}END{print "radio"radio"_stations="n+0;print "radio"radio"_auth="a+0;print "radio"radio"_assoc="s+0;print "radio"radio"_authorized="z+0}'
done
for dev in eth0 eth1 wlan0 wifi0;do
 for key in carrier rx_packets tx_packets rx_bytes tx_bytes rx_errors tx_errors rx_dropped tx_dropped;do
  printf '%s_%s=' "$dev" "$key"
  if [ "$key" = carrier ];then cat /sys/class/net/$dev/carrier 2>/dev/null || echo absent;else cat /sys/class/net/$dev/statistics/$key 2>/dev/null || echo absent;fi
 done
done
for key in eth0 eth1 wlan0 wifi0;do printf 'br0_%s=' "$key";if [ -e /sys/class/net/br0/brif/$key ];then echo 1;else echo 0;fi;done
for key in openmitrastar_auc_submit_total openmitrastar_auc_busy_total openmitrastar_gso_drop_total;do printf '%s=' "$key";cat /sys/module/qdrv/parameters/$key 2>/dev/null || echo absent;done
printf 'watchdog_control=';cat /sys/class/watchdog/watchdog0/f340_control 2>/dev/null || echo absent
printf 'fatal_count=';dmesg | grep -Eic 'MuC.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|QMAC.*fatal|DMA.*fatal|thermal.*fatal' || true
echo OM_DUAL_END
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expected-boot', required=True)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--interval', type=int, default=5)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.expected_boot):
        raise ValueError('expected boot UUID required')
    if not 1 <= args.seconds <= 600 or not 1 <= args.interval <= 60:
        raise ValueError('bounded capture seconds/interval required')
    args.output.mkdir(parents=True, exist_ok=False)
    ssh = Path(os.environ['WINDIR']) / 'System32/OpenSSH/ssh.exe'
    command = [str(ssh), '-i', str(Path.home()/'.ssh/id_ed25519'), '-b', '192.168.1.49',
               '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no',
               '-o', 'UserKnownHostsFile='+str(KNOWN_HOSTS), '-o', 'LogLevel=ERROR',
               'root@192.168.1.90', 'sh -s']
    started = time.monotonic(); samples = []; failures = []
    while True:
        request_started = time.monotonic()
        proc = subprocess.run(command, input=REMOTE.encode(), capture_output=True, timeout=20)
        stdout = proc.stdout.decode('utf8', 'replace'); stderr = proc.stderr.decode('utf8', 'replace')
        if MAC.search(stdout + stderr):
            raise RuntimeError('privacy gate: unexpected client identity; no raw output saved')
        row = {'observed_utc': datetime.now(timezone.utc).isoformat(),
               'ssh_seconds': round(time.monotonic()-request_started, 3), 'exit_code': proc.returncode}
        if proc.returncode or not stdout.startswith('OM_DUAL_BEGIN\n') or not stdout.rstrip().endswith('OM_DUAL_END'):
            failures.append({'index':len(samples), 'exit_code':proc.returncode, 'stderr':stderr[:500]})
            break
        for line in stdout.splitlines()[1:-1]:
            if '=' not in line:continue
            key,value = line.split('=',1)
            if not re.fullmatch(r'[a-zA-Z0-9_]+',key) or key in row:raise RuntimeError('unexpected output schema')
            row[key] = int(value) if re.fullmatch(r'[0-9]+',value) and key != 'watchdog_control' else value
        samples.append(row)
        (args.output/('sample-%03d.json' % (len(samples)-1))).write_text(json.dumps(row,indent=2)+'\n')
        print(json.dumps({'sample':len(samples)-1,'boot_matches':row.get('boot_id')==args.expected_boot,
                          'radio2':row.get('radio2_state'),'radio5':row.get('radio5_ping'),
                          'stations5':row.get('radio5_stations'),'fatal':row.get('fatal_count')}),flush=True)
        if row.get('boot_id') != args.expected_boot:
            failures.append({'index':len(samples)-1,'reason':'boot_changed'});break
        remaining = args.seconds-(time.monotonic()-started)
        if remaining <= 0:break
        time.sleep(min(args.interval,remaining))
    checks = {
        'ssh_complete': bool(samples) and not failures,
        'same_boot': bool(samples) and all(r.get('boot_id')==args.expected_boot for r in samples),
        'radio2_control': bool(samples) and all(r.get('radio2_state')=='ENABLED' for r in samples),
        'radio5_control': bool(samples) and all(r.get('radio5_ping')=='PONG' and r.get('radio5_rf')==1 and r.get('wifi0_carrier')==1 and r.get('radio5_frequency')=='5.18' for r in samples),
        'bridge_preserved': bool(samples) and all(r.get('br0_eth0')==r.get('br0_wlan0')==r.get('br0_wifi0')==1 for r in samples),
        'watchdog_inactive': bool(samples) and all(r.get('watchdog_control')=='00000000' for r in samples),
        'bounded_fatal_search_zero': bool(samples) and all(r.get('fatal_count')==0 for r in samples),
    }
    deltas = {}
    if len(samples)>1:
        for key,value in samples[0].items():
            if key.endswith(('_bytes','_packets','_errors','_dropped','_total')) and isinstance(value,int) and isinstance(samples[-1].get(key),int):
                deltas[key] = samples[-1][key]-value
    result = {'schema':'openmitrastar.dual-radio-readonly/v1','status':'PASS_BOUNDED_CONTROL_OBSERVATION' if all(checks.values()) else 'FAIL_OR_INCOMPLETE',
              'expected_boot':args.expected_boot,'elapsed_seconds':round(time.monotonic()-started,3),
              'samples':len(samples),'checks':checks,'failures':failures,'counter_deltas':deltas,
              'client_association_observed':any(r.get('radio5_authorized',0)>0 for r in samples),
              'traffic_gate_performed':False,'cold_boot_gate_performed':False,'physical_release_accepted':False,
              'read_only':True,'client_identities_saved':False,'ssh_host_key_pinned':True,
              'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'limits':'Bounded control/management observation. Interface counters are not source-bound client traffic, RF acceptance, throughput or release proof.'}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    return int(result['status']!='PASS_BOUNDED_CONTROL_OBSERVATION')

if __name__=='__main__':raise SystemExit(main())
