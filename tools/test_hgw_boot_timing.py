"""Compare baseline and timing candidate using isolated fake init services."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASELINE=ROOT/'work/mission-state/w4-rootfs-product/rootfs/etc/init.d/rcS'
PIN='2435abe03da459ff82f8ca77bf2a447f30c043c9e69c6da1a411702dfafc0592'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def linux(p):
    path=str(p.resolve()).replace('\\','/')
    assert path.startswith('C:/') and "'" not in path
    return '/mnt/c/'+path[3:]

def run_case(script,folder,entropy_rc,radio_rc):
    folder.mkdir(parents=True,exist_ok=False)
    services=folder/'init.d';services.mkdir()
    for name,rc in [('S05-entropy',entropy_rc),('S35-radio-modules',radio_rc),('S90-ready',0)]:
        (services/name).write_bytes(('#!/bin/sh\nexit %d\n'%rc).encode())
    state=folder/'state';state.mkdir()
    fixture=script.replace('/etc/init.d',linux(services)).replace('/run/openmitrastar',linux(state)).replace('/dev/console','/dev/stdout')
    target=folder/'rcS-fixture';target.write_bytes(fixture.encode('ascii'))
    chmod=subprocess.run(['wsl.exe','-d','REA-Linux','-e','chmod','+x',*[linux(p) for p in services.iterdir()]],capture_output=True,timeout=20)
    assert chmod.returncode==0
    proc=subprocess.run(['wsl.exe','-d','REA-Linux','-e','sh',linux(target)],capture_output=True,timeout=20)
    log=proc.stdout.decode('ascii').splitlines()
    plain=[line for line in log if not line.startswith(('OMINIT_SERVICE_TIME','OMINIT_BOOT_TIME'))]
    degraded=(state/'degraded').read_text() if (state/'degraded').exists() else ''
    return proc.returncode,plain,degraded,log

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    assert sha(BASELINE)==PIN
    args.output.mkdir(parents=True,exist_ok=False)
    baseline=BASELINE.read_text();candidate=args.candidate.read_text()
    checks=[]
    for name,entropy,radio,expected in [('healthy',0,0,0),('radio_failure_continues',0,7,0),('entropy_failure_stops',13,0,13)]:
        a=run_case(baseline,args.output/(name+'-baseline'),entropy,radio)
        b=run_case(candidate,args.output/(name+'-timed'),entropy,radio)
        assert a[:3]==b[:3] and b[0]==expected,(name,a,b)
        starts=sum('OMINIT_SERVICE_START' in line for line in b[3])
        timings=[line for line in b[3] if line.startswith('OMINIT_SERVICE_TIME')]
        assert len(timings)==starts*2
        assert all('uptime=' in line and 'uptime=unknown' not in line for line in timings)
        checks.append({'case':name,'exit_code':b[0],'service_order_and_failures_match':True,'degraded_state_matches':True,'timing_records':len(timings)})
    result={'status':'PASS_OFFLINE_BOOT_TIMING_FAKE_SERVICES','cases':checks,'candidate_sha256':sha(args.candidate),'baseline_sha256':PIN,'hardware_actions':False,'fixture_paths_substituted':True,'physical_boot_timing':False}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps(result))

if __name__=='__main__':main()
