"""Pinned SSH RAM upload/preflight and one normal non-DFS activation.

Called only while a parent PowerShell owns the HGW F319 child lease. No UART,
flash, reboot, persistent config or watchdog activation. Every run is new.
"""
import argparse
from pathlib import Path
import hashlib,json,os,re,subprocess,time

ROOT=Path(__file__).resolve().parents[1]
MAC=re.compile(r'(?i)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--mode',choices=('prepare','activate','inspect','stop'),required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    folder=args.package_dir.resolve();manifest=json.loads((folder/'manifest.json').read_text());plan=json.loads((folder/'plan.json').read_text());base=plan['remote'];boot=plan['boot_id']
    if not os.environ.get('OM_F365_RAM_CHILD_CONTEXT'):raise RuntimeError('owning hardware child lease required')
    ctx=json.loads(os.environ['OM_F365_RAM_CHILD_CONTEXT']);assert ctx['boot_id']==boot and ctx['package_sha256']==sha(folder/'package.tar') and ctx['port']=='COM4'
    assert sha(folder/'manifest.json')==plan['manifest_sha256']
    known=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f367r9-f365-transition-observation-device-bound/known_hosts.f367'
    ssh=Path(os.environ['WINDIR'])/'System32/OpenSSH/ssh.exe'
    cmd=[str(ssh),'-i',str(Path.home()/'.ssh/id_ed25519'),'-b','192.168.1.49','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=3','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'-o','LogLevel=ERROR','root@192.168.1.90']
    def execute(script,data=None,timeout=30):
        result=subprocess.run(cmd+[script if data is not None else 'sh -s'],input=data if data is not None else script.encode(),capture_output=True,timeout=timeout)
        stdout=MAC.sub('[MAC-REDACTED]',result.stdout.decode('utf8','replace'));stderr=MAC.sub('[MAC-REDACTED]',result.stderr.decode('utf8','replace'))
        return result.returncode,stdout,stderr
    checks=[];started=time.monotonic()
    def record(stage,row):
        rc,stdout,stderr=row;(args.output/(stage+'.stdout')).write_text(stdout);(args.output/(stage+'.stderr')).write_text(stderr);checks.append({'stage':stage,'exit_code':rc,'stdout':stdout,'stderr':stderr});print(json.dumps({'stage':stage,'exit_code':rc,'stdout':stdout,'stderr':stderr}),flush=True);return rc
    status='FAILED'
    try:
        guard="set -eu; test \"$(cat /proc/sys/kernel/random/boot_id)\" = '"+boot+"'; "
        if args.mode=='prepare':
            if record('admission',execute(guard+"test ! -e /sys/module/qdrv; test ! -e /sys/class/net/wifi0; test ! -e '"+base+"'; test \"$(cat /sys/class/watchdog/watchdog0/f340_control)\" = 00000000; echo RAM_ADMISSION_PASS\n")):raise RuntimeError('admission failed')
            target=base+'-package.tar';digest=sha(folder/'package.tar')
            upload="umask 077; test ! -e '"+target+"' && cat > '"+target+"'"
            if record('upload',execute(upload,(folder/'package.tar').read_bytes(),60)):raise RuntimeError('upload failed')
            unpack=guard+"test \"$(sha256sum '"+target+"' | awk '{print $1}')\" = '"+digest+"'; mkdir '"+base+"'; tar -xf '"+target+"' -C '"+base+"'; /bin/ash '"+base+"/bin/guard' preflight\n"
            if record('preflight',execute(unpack,timeout=60)):raise RuntimeError('preflight failed')
            status='PASS_RAM_PACKAGE_UPLOADED_PREFLIGHT'
        elif args.mode=='activate':
            if record('activation',execute(guard+"OM_F365_RAM_AUTH_BOOT='"+boot+"' /bin/ash '"+base+"/bin/guard' activate\n",timeout=150)):raise RuntimeError('activation failed')
            if record('independent-inspect',execute(guard+"/bin/ash '"+base+"/bin/guard' inspect; printf 'fatal='; dmesg | grep -Eic 'MuC.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access' || true\n")):raise RuntimeError('readback failed')
            assert 'fatal=0' in checks[-1]['stdout']
            if record('keep-running',execute(guard+"test \"$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)\" = 1; : > '"+base+"/keep-running'; echo RAM_KEEP_RUNNING_PASS\n")):raise RuntimeError('keep failed')
            status='PASS_5G_RAM_CONTROL_PLANE_RUNNING'
        else:
            if record(args.mode,execute(guard+"/bin/ash '"+base+"/bin/guard' "+args.mode+"\n",timeout=45)):raise RuntimeError(args.mode+' failed')
            status='PASS_'+args.mode.upper()
    except Exception as error:
        checks.append({'error':type(error).__name__,'message':str(error)})
    result={'schema':'openmitrastar.f365-ram-executor/v1','status':status,'mode':args.mode,'elapsed_seconds':round(time.monotonic()-started,3),'package_sha256':sha(folder/'package.tar'),'manifest_sha256':sha(folder/'manifest.json'),'boot_id':boot,'checks':checks,'flash_writes':False,'reboot_requested':False,'watchdog_arm':False,'client_pass':False,'traffic_pass':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':status,'result':str(args.output/'result.json')}),flush=True);return int(status=='FAILED')

if __name__=='__main__':raise SystemExit(main())
