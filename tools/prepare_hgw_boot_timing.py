"""Derive rcS timing-only instrumentation offline from the live matched source."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'work/mission-state/w4-rootfs-product/rootfs/etc/init.d/rcS'
PIN = '2435abe03da459ff82f8ca77bf2a447f30c043c9e69c6da1a411702dfafc0592'

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    raw = SOURCE.read_bytes()
    if sha(raw)!=PIN:raise ValueError('live-matched rcS source drift')
    source = raw.decode('ascii')
    addition = '''boot_uptime()
{
\tom_boot_uptime=unknown
\tIFS=' ' read -r om_boot_uptime om_boot_idle </proc/uptime || om_boot_uptime=unknown
\tcase "$om_boot_uptime" in
\t''|*[!0-9.]*) om_boot_uptime=unknown ;;
\tesac
}

'''
    old = "console_log 'OMINIT_START schema=1'"
    assert source.count(old)==1
    candidate = source.replace(old, addition+old)
    start = '\tconsole_log "OMINIT_SERVICE_START name=$name"'
    end = '\tconsole_log "OMINIT_SERVICE_END name=$name rc=$rc"'
    assert candidate.count(start)==candidate.count(end)==1
    candidate = candidate.replace(start, '\tboot_uptime\n'+start+'\n\tconsole_log "OMINIT_SERVICE_TIME phase=start name=$name uptime=$om_boot_uptime"')
    candidate = candidate.replace(end, '\tboot_uptime\n'+end+'\n\tconsole_log "OMINIT_SERVICE_TIME phase=end name=$name rc=$rc uptime=$om_boot_uptime"')
    candidate = candidate.replace("console_log 'OMINIT_END'", "boot_uptime\nconsole_log 'OMINIT_END'\nconsole_log \"OMINIT_BOOT_TIME phase=end uptime=$om_boot_uptime\"")
    # Prove the original statements are all byte-for-byte preserved after
    # deleting just the declared instrumentation; status capture stays adjacent.
    restored = candidate.replace(addition, '').replace('\tboot_uptime\n', '')
    restored = '\n'.join(line for line in restored.split('\n')
                         if 'OMINIT_SERVICE_TIME' not in line and 'OMINIT_BOOT_TIME' not in line)
    restored = restored.replace("boot_uptime\nconsole_log 'OMINIT_END'", "console_log 'OMINIT_END'")
    assert restored==source
    assert '\t"$service" start\n\trc=$?\n\tboot_uptime' in candidate
    out = ROOT/'outputs/rea/arc700-20261021-r2'/('boot-timing-candidate-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    target = out/'rcS'
    target.write_bytes(candidate.encode('ascii'))
    wsl_target = '/mnt/c/'+str(target).replace('\\','/')[3:]
    check = subprocess.run(['wsl.exe','-d','REA-Linux','-e','sh','-n',wsl_target],capture_output=True,timeout=20)
    result = {'status':'PASS_OFFLINE_TIMING_ONLY' if check.returncode==0 else 'FAIL_OFFLINE_SYNTAX',
              'source':str(SOURCE),'source_sha256':PIN,'candidate_sha256':sha(target.read_bytes()),
              'original_statements_preserved':True,'service_status_capture_unchanged':True,
              'service_order_unchanged':True,'retry_deadlines_unchanged':True,
              'hardware_actions':False,'installed':False,'boot_speed_improvement_proven':False,
              'syntax_exit_code':check.returncode}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='ascii')
    print(json.dumps({'directory':str(out),**result}))
    return check.returncode

if __name__=='__main__':raise SystemExit(main())
