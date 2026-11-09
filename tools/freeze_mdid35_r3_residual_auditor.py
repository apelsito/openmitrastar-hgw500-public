"""R3frozen strictmodule auditor same exact diagnostics/tables as retainedr2."""
import argparse,hashlib,json
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--r2-auditor',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);text=a.r2_auditor.read_text();assert text.count('mdid494-ft495-source35-20261022T230700Z-r2')==1;text=text.replace('mdid494-ft495-source35-20261022T230700Z-r2','mdid494-ft495-source35-20261022T232500Z-r3');text=text.replace('PASS_COMPLETE_MDID35_R2_SEED_MATCHED_HEADER_RESIDUAL_SCOPE','PASS_COMPLETE_MDID35_R3_MATCHED_HEADER_RESIDUAL_SCOPE');script=a.output/'strict-auditor.py';script.write_text(text);r={'status':'FROZEN_MDID35_R3_RESIDUAL_AUDITOR_PENDING_CURRENT_MODULE_GATE','hardware_accessed':False,'firmware_eligible':False,'pins':{str(x):sha(x)for x in[Path(__file__),a.r2_auditor,script]}};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
