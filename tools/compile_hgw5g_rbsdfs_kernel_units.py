"""Compilefouractual32changedunits with pre-pinned .inc context, offline.

RetainedfullSOURCE30headers/compiler/providerdependenciesplusnewinc/helpers
are pinnedbeforecompile andcheckedbefore/after. No module/hardwareclaim.
"""
import argparse,hashlib,json,os
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-pins',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);pins=json.loads(a.parent_pins.read_text())
 for path,h in pins.items():assert sha(path)==h
 for root in['source','headers']:
  for path in(a.candidate/root).rglob('*'):
   if path.is_file():pins[str(path)]=sha(path)
 for path in[Path(__file__),Path(b.__file__),a.candidate/'result.json',a.parent_pins]:pins[str(path)]=sha(path)
 canonical={b.key(path)for path in pins};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');q,w,h=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';rows=[]
 for c,n in [('qdrv','qdrv_wlan'),('qdrv','qdrv_radar'),('wlan','ieee80211'),('wlan','ieee80211_wireless')]:
  folder=a.output/c;folder.mkdir(exist_ok=True);cmd,src=b.compile_command(c,n,folder,q,w,h);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+n));ds=b.readdeps(folder/(n+'.d'));assert not {b.key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-canonical,'unpinned '+n;obj=folder/(n+'.o');rows.append({'component':c,'name':n,'source_sha256':sha(src),'object_sha256':sha(obj),'object_bytes':obj.stat().st_size});print(json.dumps(rows[-1]),flush=True)
 for path,h in pins.items():assert sha(path)==h
 r={'status':'PASS_ARC_RBSDFS_KERNEL_FOUR_TYPED_UNITS_ONLY_PROVIDER_UNBOUND','hardware_accessed':False,'firmware_eligible':False,'units':rows,'input_pins':len(pins),'inputs_unchanged':True,'limits':'4units only; nojoint/fullmodule/sourcecompatibilityacceptance.'};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
