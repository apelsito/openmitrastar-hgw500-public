"""Seal the completed peer and its original-header provenance without rebuilding."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
PRIOR=Path('/workspace/OpenMitraStar-build/f367r9/f367r9-transition-20260922T222943Z')
BUILD='/home/user/openmitrastar-build/f367r9-transition-20260922T222943Z/a/wlan'
PEER=ROOT/'work/linux510-radio-port/quantenna/wlan'
SOURCE=ROOT/'work/kernel-port/f367r9-transition-observation'
REUSE=Path('/workspace/OpenMitraStar-build/f367r7/f367r7-clock-20260922T193754Z/result.json')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def item(p):p=Path(p);return dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=sha(p))
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def main():
 reuse=json.loads(REUSE.read_text());assert sha(PEER/'wlan.ko')==reuse['modules']['wlan']['sha256']
 header=ROOT/'work/linux510-radio-port/quantenna/qdrv/qdrv_dma_wire.h';sealed_header=ROOT/'work/kernel-port/f367r7-clock-publication/qdrv/qdrv/qdrv_dma_wire.h'
 assert sha(header)==sha(sealed_header)
 cmd=PEER/'.ieee80211_beacon_desc.o.cmd';assert '../qdrv/qdrv_dma_wire.h' in cmd.read_text()
 macro_flags=sorted(set(re.findall(r'-DOPENMITRASTAR_[A-Za-z0-9_=]+',cmd.read_text().splitlines()[0])))
 assert macro_flags==sorted(set(re.findall(r'-DOPENMITRASTAR_[A-Za-z0-9_=]+',(PEER/'.ieee80211_wireless.o.cmd').read_text().splitlines()[0])))
 source_pins={str(p.resolve()):sha(p) for p in (SOURCE/'wlan').iterdir() if p.is_file()}
 for path,digest in source_pins.items():assert sha(PRIOR/'source/wlan'/Path(path).name)==digest
 out=ROOT/'outputs/kernel-port'/('f367r9-peer-sealed-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 for name in ('wlan.ko','Module.symvers'):
  subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','cp',BUILD+'/'+name,linux(out/name)],check=True)
 pins={**source_pins,**{str(p.resolve()):sha(p) for p in (Path(__file__),PEER/'wlan.ko',header,sealed_header,cmd,PEER/'.ieee80211_wireless.o.cmd',PRIOR/'build.sh',REUSE)}}
 report=dict(schema='openmitrastar.f367r9-peer-provenance/v1',status='PASS_PEER_SOURCE_AND_HEADER_PROVENANCE',artifact=item(out/'wlan.ko'),module_symvers=item(out/'Module.symvers'),source_pins=source_pins,input_pins=pins,previous_wlan=item(PEER/'wlan.ko'),previous_wlan_matches_r8=True,dma_header=item(header),dma_header_matches_sealed_r7=True,original_compile_command=item(cmd),parent_macro_flags=macro_flags,completed_build_directory=BUILD,wlan_build_count=1,wlan_double_build_verified=False,no_baseline_recompilation=True,hardware_actions=False)
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(result=str(out/'result.json'),artifact=report['artifact'],status=report['status'],wlan_build_count=1),indent=2))
if __name__=='__main__':main()
