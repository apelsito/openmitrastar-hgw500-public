"""Exact SOURCE23 C bodies with R12 matching host headers, analysis-only control."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);shutil.copytree(a.base/'source',a.output/'source');shutil.copytree(a.candidate/'headers',a.output/'headers')
 # Extrahelperfile is unreferenced by originalSOURCE23 bodies, preservedforwireheaders.
 shutil.copyfile(a.candidate/'source/wlan/openmitrastar_bss_tm.h',a.output/'source/wlan/openmitrastar_bss_tm.h')
 result={'status':'SOURCE_ONLY_EXACT_SOURCE23_MATCHED_R12_HEADER_CONTROL_NOT_FIRMWARE','hardware_accessed':False,'firmware_eligible':False,'base_source':str(a.base),'matched_headers':str(a.candidate),'C_bodies_exact_SOURCE23':True,'limits':'EnclosingABIchanged analysiscontrolonly; originalSOURCE23module cannotmixwithR12headers. No operational/releaseclaim.','pins':{str(p):sha(p)for p in[Path(__file__),a.base/'result.json',a.candidate/'result.json']}}
 for p in(a.base/'source').rglob('*.c'):assert sha(p)==sha(a.output/p.relative_to(a.base))
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
