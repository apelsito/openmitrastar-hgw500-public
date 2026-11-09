"""Validate the inert F344 bootstrap artifact without executing it."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f331_oem_postfilter_projection import linux
from f344_runtime_contract import native_start,driver_contract
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'outputs/preflight'/('f344-bootstrap-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 donor=ROOT/'versions/lyoko-foundation-6.9.0-f315-radar-shadow/overlay/usr/sbin/om-radio5-start';data=native_start(donor.read_bytes());s=data.decode();(out/'om-radio5-start-f344').write_bytes(data)
 checks=[s.count('openmitrastar_mode_workflow=1')==3,'load_module wlan_scan_sta.ko' in s,'hardware_enable=0 diagnostic_capture=0 authoritative_enable=0' in s,'hardware_enable=1' not in s,'shadow_arm' not in s,'om-radar-engine' not in s,s.index('--launch-ap')<s.index('--confirm-bootstrap')<s.index('rm -f "$conf"'),'/usr/sbin/hostapd-qtn -dd' not in s,'mode=managed' not in s]
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh','-n',linux(out/'om-radio5-start-f344')],capture_output=True,text=True,timeout=20);checks.append(p.returncode==0)
 keys={'QDRV_SHA256':'qdrv','WLAN_SHA256':'wlan','BOARD_COMPAT_SHA256':'board_compat','SWITCH_EMAC_SHA256':'switch_emac','SWITCH_TQE_SHA256':'switch_tqe'};modules={n:{'sha256':'a'*64} for n in (*keys.values(),'qtn_radar_f338')};input=('\n'.join(k+'='+'0'*64 for k in keys)+'\nUNRELATED=preserved\n').encode();rendered=driver_contract(input,modules)
 checks.extend([b'UNRELATED=preserved\n' in rendered,b'RADAR_F338_SHA256='+b'a'*64 in rendered,rendered.count(b'QDRV_SHA256=')==1])
 try:native_start(donor.read_bytes()+b'\n');checks.append(False)
 except ValueError:checks.append(True)
 result={'status':'PASS_BOOTSTRAP_TRANSFORM_INERT' if all(checks) else 'FAIL','checks':len(checks),'failures':[i for i,v in enumerate(checks,1) if not v],'loader_sha256':hashlib.sha256(data).hexdigest(),'loader':str(out/'om-radio5-start-f344'),'hardware':False,'loader_executed':False,'production_boot_wiring':'NOT_INSTALLED','wifi':'USER_DEFERRED','stderr':p.stderr};(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return not all(checks)
if __name__=='__main__':raise SystemExit(main())
