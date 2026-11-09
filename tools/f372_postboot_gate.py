"""Strict F372 postboot identity/control gate; offline by default.

--observe reads the owner-authorized HGW using pinned SSH. It never changes
runtime, starts/stops radios, reboots, flashes or opens UART. The gate excludes
client traffic, cold boot, recovery and release acceptance.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
FIRMWARE=DEVICE/'firmware/f372-f371-auc-tqe-observation-device-bound'
MANIFEST_SHA='e4d9502d90fcb64c289c8369c41231a9dd837e05d2133e13953d3482b6abe0b5'
IMAGE_SHA='e8f7315c286e98d73f6bf4152c652f4633c8f63bd4a72b8a300e6859af619ef9'
QDRV_SHA='d5e1f58303eaaa02123e0cf6352bd40c40df3027be300d2a1143b07f54a05dae'
VERSION='lyoko-foundation-6.12.3-f372-auc-tqe-observation-device'
STORE_SHA='fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873'
CONFIG_SHA='073747246e193ebca532b2de35b78a27a1930a908e0717f5706a682fa44457a9'
PARAMS=('openmitrastar_auc_busy_free','openmitrastar_auc_raw_ok',
        'openmitrastar_auc_raw_other','openmitrastar_auc_return_success')
QUAL=ROOT/'outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2/qualification-20261021T222300Z'
QUAL_SHA='149f8f10743aa82907a82615d9adb9e5c23f1d6c61661a33b6dc7e44e3ee7ad2'
PARAM_METADATA_SHA='29b37079e8a15e4c51424eb972cb6f9206bf393461078cc471277d93c9425a0d'
UUID=re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
MAC=re.compile(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inputs():
    if sha(FIRMWARE/'manifest.json')!=MANIFEST_SHA:raise ValueError('manifest drift')
    m=json.loads((FIRMWARE/'manifest.json').read_text())
    image=FIRMWARE/m['artifacts']['webformat']['file']
    if sha(image)!=IMAGE_SHA or image.stat().st_size!=5382144:raise ValueError('image drift')
    if sha(QUAL/'result.json')!=QUAL_SHA or sha(QUAL/'module-parameters.json')!=PARAM_METADATA_SHA:
        raise ValueError('module qualification drift')
    q=json.loads((QUAL/'result.json').read_text());p=json.loads((QUAL/'module-parameters.json').read_text())
    if q['status']!='PASS_OFFLINE_COMPLETE_MODULE' or q['module']['sha256']!=QDRV_SHA:
        raise ValueError('module not qualified')
    versions=p['metadata']['srcversion']
    if len(versions)!=1 or not re.fullmatch('[0-9A-F]{1,24}',versions[0]):raise ValueError('srcversion identity')
    bindings=m['runtime_bindings']
    if bindings['/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko']!=QDRV_SHA:
        raise ValueError('module binding drift')
    for path,digest in bindings.items():
        if not re.fullmatch('/[A-Za-z0-9_./:-]+',path) or '..' in path.split('/') or not re.fullmatch('[0-9a-f]{64}',digest):
            raise ValueError('unsafe binding path')
    return m,versions[0]

def remote_script(bindings):
    # Actual program outputs are hashes/counts only. Never dump hostapd settings,
    # calibration bytes, PSKs, client MACs or raw factory partitions.
    lines=[r'''echo F372_POSTBOOT_BEGIN
printf 'boot=';cat /proc/sys/kernel/random/boot_id
printf 'kernel=';uname -r
printf 'uts=';uname -v
printf 'version=';sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'ready=';cat /run/openmitrastar/boot-state
printf 'root_ro=';awk '$2=="/"&&$3=="squashfs" {n++;if(index(","$4",",",ro,"))ok++}END{print (n==1&&ok==1)?1:0}' /proc/mounts
printf 'store_ro=';flags=$(cat /sys/class/mtd/mtd4/flags 2>/dev/null || echo unknown);case "$flags" in 0x[0-9a-fA-F]*|[0-9]*) printf '%s\n' "$(( (flags & 0x400) == 0 ))";; *) echo unknown;; esac
printf 'store=';sha256sum /dev/mtd4 | awk '{print $1}'
printf 'config=';sha256sum /run/openmitrastar/config/active.conf | awk '{print $1}'
printf 'watchdog=';cat /sys/class/watchdog/watchdog0/f340_control
printf 'radio2=';/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | sed -n 's/^state=//p'
printf 'radio5=';/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping
printf 'rf=';cat /sys/module/qdrv/parameters/openmitrastar_rf_enable
printf 'carrier=';cat /sys/class/net/wifi0/carrier
printf 'frequency=';/usr/sbin/iwconfig-qtn wifi0 2>/dev/null | sed -n 's/.*Frequency:\([0-9.]*\) GHz.*/\1/p'
printf 'srcversion=';cat /sys/module/qdrv/srcversion
for n in eth0 wlan0 wifi0;do printf 'bridge_%s=' "$n";if [ -e /sys/class/net/br0/brif/$n ];then echo 1;else echo 0;fi;done
printf 'eth0_carrier=';cat /sys/class/net/eth0/carrier
printf 'lifetime_retained=';sed -n 's/^retained=//p' /sys/devices/qdrv/lifetime_state
printf 'qdrv_boot_failed=';sed -n 's/^boot_failed=//p' /sys/devices/qdrv/lifetime_state
printf 'country=';/usr/sbin/iwpriv-qtn wifi0 get_region 2>/dev/null | sed -n 's/.*get_region:\([0-9]*\).*/\1/p'
printf 'fatal=';dmesg | grep -Eic 'MuC.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|QMAC.*fatal|DMA.*fatal|thermal.*fatal' || true
''']
    for i,path in enumerate(sorted(bindings)):
        lines.append("printf 'file_%d=';sha256sum '%s' | awk '{print $1}'"%(i,path))
    for p in PARAMS:
        lines.append("printf '%s=';cat /sys/module/qdrv/parameters/%s"%(p,p))
        lines.append("printf '%s_perm=';ls -l /sys/module/qdrv/parameters/%s | awk 'NR==1{print $1}'"%(p,p))
    lines.append('echo F372_POSTBOOT_END\n')
    return '\n'.join(lines)

def evaluate(text,bindings,srcversion,previous_boot):
    if not UUID.fullmatch(previous_boot):raise ValueError('previous boot UUID required')
    if len(text)>131072 or MAC.search(text):raise ValueError('privacy/size gate')
    lines=text.strip().splitlines()
    if not lines or lines[0]!='F372_POSTBOOT_BEGIN' or lines[-1]!='F372_POSTBOOT_END':raise ValueError('missing exact transcript boundary')
    values={}
    for line in lines[1:-1]:
        if '=' not in line:raise ValueError('invalid transcript line')
        key,value=line.split('=',1)
        if key in values or not re.fullmatch('[A-Za-z0-9_]+',key):raise ValueError('duplicate/invalid field')
        values[key]=value
    expected={'kernel':'5.10.260-openmitrastar-radiohw','uts':'#358 @1790006400','version':VERSION,'ready':'ready',
              'root_ro':'1','store_ro':'1','store':STORE_SHA,'config':CONFIG_SHA,'watchdog':'00000000',
              'radio2':'ENABLED','radio5':'PONG','rf':'1','carrier':'1','frequency':'5.18','srcversion':srcversion,
              'bridge_eth0':'1','bridge_wlan0':'1','bridge_wifi0':'1','eth0_carrier':'1',
              'lifetime_retained':'1','qdrv_boot_failed':'0','country':'21317','fatal':'0'}
    expected.update({'file_%d'%i:bindings[path] for i,path in enumerate(sorted(bindings))})
    checks={key:values.get(key)==value for key,value in expected.items()}
    checks['new_boot']=bool(UUID.fullmatch(values.get('boot',''))) and values['boot']!=previous_boot
    fields=set(expected)|{'boot'}
    counters={}
    for p in PARAMS:
        fields.update((p,p+'_perm'))
        checks[p+'_value']=bool(re.fullmatch('[0-9]+',values.get(p,''))) and int(values.get(p,'0'))<=0xffffffff
        checks[p+'_readonly']=values.get(p+'_perm')=='-r--r--r--'
        if checks[p+'_value']:counters[p]=int(values[p])
    checks['exact_field_set']=set(values)==fields
    return {'schema':'openmitrastar.f372-postboot-control/v1','status':'PASS_CONTROL_ONLY' if all(checks.values()) else 'FAIL',
            'checks':checks,'boot_id':values.get('boot'),'previous_boot':previous_boot,'counters':counters,
            'failed_checks':[key for key,value in checks.items() if not value],
            'radio_client_gate':False,'source_bound_traffic_gate':False,'cold_boot_repeatability_gate':False,
            'protected_physical_readback_gate':False,'recovery_gate':False,'release_pass':False}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--previous-boot',required=True);parser.add_argument('--output',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--transcript',type=Path);mode.add_argument('--observe',action='store_true')
    args=parser.parse_args();m,srcversion=inputs();script=remote_script(m['runtime_bindings'])
    args.output.mkdir(parents=True,exist_ok=False)
    if args.observe:
        known=FIRMWARE/'known_hosts.f372';ssh=Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'
        cmd=[str(ssh),'-i',str(Path.home()/'.ssh/id_ed25519'),'-b','192.168.1.49','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','StrictHostKeyChecking=yes','-o','UpdateHostKeys=no','-o','UserKnownHostsFile='+str(known),'-o','LogLevel=ERROR','root@192.168.1.90','sh -s']
        proc=subprocess.run(cmd,input=script.encode(),capture_output=True,timeout=90)
        text=proc.stdout.decode('utf8','strict');stderr=proc.stderr.decode('utf8','replace')
        if MAC.search(text+stderr):raise ValueError('privacy gate: raw transcript not saved')
        (args.output/'stderr.txt').write_text(stderr)
        if proc.returncode:raise RuntimeError('SSH observation failed; no acceptance')
    else:text=args.transcript.read_text()
    result=evaluate(text,m['runtime_bindings'],srcversion,args.previous_boot)
    result.update(observed_utc=datetime.now(timezone.utc).isoformat(),observation_executed=args.observe,
                  manifest_sha256=MANIFEST_SHA,image_sha256=IMAGE_SHA,script_sha256=sha(Path(__file__)))
    (args.output/'transcript.txt').write_text(text);(args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));return int(result['status']!='PASS_CONTROL_ONLY')

if __name__=='__main__':raise SystemExit(main())
