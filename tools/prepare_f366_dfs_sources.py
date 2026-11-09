"""Prepare a versioned native DFS diagnostic on F364/F365, offline only."""
from pathlib import Path
import hashlib,json,shutil
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'work/kernel-port/f366'
QBASE=ROOT/'work/linux510-radio-port/quantenna-f364-lifetime'
RADAR=ROOT/'work/linux510-radio-port/quantenna-f338-availability'
PROVIDER=ROOT/'work/kernel-port/f341'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def main():
 require(not DEST.exists(),'immutable F366 source already exists')
 require(shutil.disk_usage(ROOT).free>500*1024*1024,'C space guard')
 DEST.mkdir(parents=True)
 shutil.copytree(QBASE,DEST/'qdrv')
 for sub in ('kernel','uapi'):shutil.copytree(PROVIDER/sub,DEST/sub)
 for p in (DEST/'kernel').iterdir():
  if p.is_file():p.write_bytes(p.read_bytes().replace(b'qtn_radar_f341',b'qtn_radar_f366').replace(b'openmitrastar_radar_f341',b'openmitrastar_radar_f366').replace(b'OMF341',b'OMF366'))
 for name in ('qdrv_radar.c','qdrv_f332_ready.inc','qdrv_f338_availability.inc'):
  shutil.copyfile(RADAR/'qdrv'/name,DEST/'qdrv/qdrv'/name)
 shutil.copytree(RADAR/'tests',DEST/'qdrv/tests')
 p=DEST/'qdrv/qdrv/Makefile';s=p.read_text();require(s.count(' qdrv_radar_compat.o ')==1,'compat object anchor');p.write_bytes(s.replace(' qdrv_radar_compat.o ',' ').encode())
 # F355 rejects teardown once retained. The unretained path still must join
 # provider and qdrv callbacks before freeing any radio/shared context.
 p=DEST/'qdrv/qdrv/qdrv_soc.c';s=p.read_text();body=extract(s,'qdrv_soc_exit')
 anchor='\tif(!qcb||!qcb->resources)return 0;'
 require(body.count(anchor)==1,'lifetime retained guard anchor')
 new=body.replace(anchor,anchor+'\n\t/* F338 native provider drain; never free shared state after a failed join. */\n\tif (qdrv_radar_exit(&qcb->macs[0]) != 0)\n\t\treturn -EBUSY;',1)
 p.write_bytes(s.replace(body,new,1).encode())
 baseline={p.relative_to(QBASE).as_posix():sha(p) for p in QBASE.rglob('*') if p.is_file()}
 current={p.relative_to(DEST/'qdrv').as_posix():sha(p) for p in (DEST/'qdrv').rglob('*') if p.is_file()}
 changes=sorted(n for n in set(baseline)|set(current) if baseline.get(n)!=current.get(n))
 allowed={'qdrv/Makefile','qdrv/qdrv_radar.c','qdrv/qdrv_f332_ready.inc','qdrv/qdrv_f338_availability.inc','qdrv/qdrv_soc.c','tests/test_ready.c'}
 require(set(changes)==allowed,'unexpected qdrv source changes '+str(set(changes)^allowed))
 for n in ('qdrv_get_internal_temp','qdrv_wps_button_read'):
  filename='qdrv_wlan.c' if n=='qdrv_get_internal_temp' else 'qdrv_control.c'
  # WPS lives elsewhere in some profiles; whole unchanged source pins below
  # retain every file other than the exact native radar delta.
  if n in (QBASE/'qdrv'/filename).read_text():require(extract((QBASE/'qdrv'/filename).read_text(),n)==extract((DEST/'qdrv/qdrv'/filename).read_text(),n),'unrelated sensor/WPS function changed')
 for name in ('f355_lifetime.h','qdrv_f355_lifetime.h','qdrv_f355_lifetime.c','qdrv_control.c','qdrv_module.c','qdrv_hostlink.c','qdrv_wlan.c'):
  require(sha(QBASE/'qdrv'/name)==sha(DEST/'qdrv/qdrv'/name),'F355/F363 source changed '+name)
 require(b'#define F338_RELEASE_QUALIFIED 0' in (DEST/'kernel/f332_provider.c').read_bytes(),'release authority must remain disabled')
 pins={p.relative_to(DEST).as_posix():sha(p) for p in DEST.rglob('*') if p.is_file()}
 result={'schema':'openmitrastar.f366-dfs-source/v1','status':'PASS_VERSIONED_NATIVE_RADAR_SOURCE_COMBINATION','source':str(DEST),'source_pins':pins,'qdrv_baseline':str(QBASE),'qdrv_baseline_pins':baseline,'qdrv_changed_files':changes,'native_donor':str(RADAR),'provider_donor':str(PROVIDER),'provider_changes':'module/proc/log identity only; wire ABI F338 unchanged','f355_lifetime_sources_exact':True,'f363_thermal_and_wps_sources_exact':True,'authority_compiled_off':True,'hardware_actions':False}
 (DEST/'source-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'status':result['status'],'source':str(DEST),'manifest_sha256':sha(DEST/'source-manifest.json')}))
if __name__=='__main__':main()
