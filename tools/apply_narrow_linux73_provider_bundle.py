"""Compose one new narrowprovidercompilebundle beforeits firstbuild only."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--narrow',type=Path,required=True);a=p.parse_args();assert not any(a.bundle.rglob('*.o'));before=a.bundle/'providers/qtn_platform_support.c';new=a.narrow/'providers/qtn_platform_support.c';oldsha=sha(before);shutil.copyfile(new,before);r={'status':'SOURCE_ONLY_NARROW_PLATFORM_APPLIED_BEFORE_FIRST_73_BUNDLE_COMPILE','hardware_accessed':False,'firmware_eligible':False,'old_sha256':oldsha,'new_sha256':sha(before),'narrow_result_sha256':sha(a.narrow/'result.json')};(a.bundle/'narrow-composition.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
