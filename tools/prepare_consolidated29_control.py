"""Create SOURCE25 same-header control for combined29, analysis-only."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);shutil.copytree(a.base/'source',a.output/'source');shutil.copytree(a.candidate/'headers',a.output/'headers');shutil.copyfile(a.candidate/'source/wlan/openmitrastar_bss_tm.h',a.output/'source/wlan/openmitrastar_bss_tm.h')
 result={'status':'SOURCE_ONLY_EXACT_COC25_COMBINED29_HEADER_CONTROL','hardware_accessed':False,'firmware_eligible':False,'base':str(a.base),'candidate_headers':str(a.candidate),'source_C_exact_CoC25':True,'pins':{str(p):sha(p)for p in[Path(__file__),a.base/'result.json',a.candidate/'result.json']},'limits':'Controlsource only; nofirmware/release/candidatefeatureacceptance.'}
 for p in(a.base/'source').rglob('*.c'):assert sha(p)==sha(a.output/p.relative_to(a.base))
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
