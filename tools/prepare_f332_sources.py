"""Seed a new F332 directory from accepted source components; no hardware."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/kernel-port/modules/f332_dfs_provider'
def main():
 if OUT.exists():raise SystemExit('preserve existing F332 sources')
 OUT.mkdir();(OUT/'engine').mkdir();(OUT/'provider').mkdir();(OUT/'tests').mkdir()
 copied={}
 for old,new in (
  ('f328_oem_classifier/f328_legacy_abi.c','engine/f328_legacy_abi.c'),
  ('f328_oem_classifier/f328_legacy_abi.h','engine/f328_legacy_abi.h'),
  ('f330_oem_preprocess/f330_preprocess.h','provider/f330_preprocess.h'),
  ('f331_postfilter/f331_postfilter.h','provider/f331_postfilter.h'),
  ('f327_radar_event_lifecycle/f327_oem_requests.h','provider/f327_oem_requests.h'),
  ('f316_radar_classifier/f316_portable.h','provider/f316_portable.h')):
  source=ROOT/'work/kernel-port/modules'/old;target=OUT/new;data=source.read_bytes();target.write_bytes(data)
  copied[old]={'sha256':hashlib.sha256(data).hexdigest(),'copy':new}
 (OUT/'copied-sources.json').write_text(json.dumps(copied,indent=2)+'\n')
 print(OUT)
if __name__=='__main__':main()
