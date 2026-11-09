"""SOURCE32 originalC with MDID35VAPheaders asanalysis-only matchingcontrol."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.candidate/'headers',a.output/'headers');shutil.copyfile(a.candidate/'source/wlan/openmitrastar_mdie.h',a.output/'source/wlan/openmitrastar_mdie.h');r={'status':'SOURCE_ONLY_EXACT32_C_WITH_MDID35_SHARED_HEADER_CONTROL','hardware_accessed':False,'firmware_eligible':False,'parent':str(a.parent),'headers':str(a.candidate),'C_bodies_exact_parent32':True,'limits':'ControlhasnewVAPsizeofonly; notfirmware/modulefeatureacceptance.','pins':{str(p):sha(p)for p in[Path(__file__),a.parent/'result.json',a.candidate/'result.json']}};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
