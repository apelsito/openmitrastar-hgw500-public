"""Create source-identical parentcontrol with onlycandidateheader overlay.

Allowswholemoduleaudit of globalIC/VAPstructure effects without broadbinarymask.
Newdirectoryonly, nooriginalchange. Controlimage is notfunctionalcandidate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.candidate/'headers',a.output/'headers')
 files={str(x.relative_to(a.output)):sha(x)for x in(a.output/'source').rglob('*')if x.is_file()and x.suffix in('.c','.h')};assert all(sha(a.parent/p)==h for p,h in files.items())
 result=dict(status='SOURCE_IDENTICAL_PARENT_WITH_CANDIDATE_HEADERS_ANALYSIS_CONTROL',hardware_accessed=False,firmware_eligible=False,parent=str(a.parent),candidate=str(a.candidate),source_pins=files,header_pins={str(x.relative_to(a.output)):sha(x)for x in(a.output/'headers').rglob('*')if x.is_file()},limits='Sourcecontrolnotreleasecandidate; actualfullcompile neededtoreconcileoffseteffects')
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status=result['status'],files=len(files))))
if __name__=='__main__':main()
