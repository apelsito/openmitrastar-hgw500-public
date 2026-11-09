"""Admit SOURCE30 incrementalreceipt to retained strictjoint composer.

Frozenoriginalcopiedintoevidence; onlyexactreceiptadmission adapted. NoHW.
"""
import argparse,hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source-build',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--lane',choices=['a','b'],required=True);p.add_argument('--qdrv-baseline',type=Path,required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/compose_hgw5g_joint_modules_dedup.py';text=original.read_text();old='("NO_GO_TYPED_HEADER_CLOSURE", "PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA")';assert text.count(old)==1;text=text.replace(old,'("PASS_CONSOLIDATED30_FOUR_REAL_UNITS_PAIRED_EXACT_PARENT_CLOSURE",)',1);script=a.output/'adapted-strict-composer.py';script.write_text(text);env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools');cmd=[sys.executable,str(script),'--source-build',str(a.source_build),'--candidate',str(a.candidate),'--lane',a.lane,'--qdrv-baseline-build',str(a.qdrv_baseline),'--wlan-baseline-build',str(a.wlan_baseline),'--output',str(a.output/'joint')];r=subprocess.run(cmd,env=env,capture_output=True);(a.output/'compose.stdout').write_bytes(r.stdout);(a.output/'compose.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads((a.output/'joint/result.json').read_text());assert proof['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS';proof['adaptation_pins']={str(p):sha(p)for p in[Path(__file__),original,script]};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':main()
