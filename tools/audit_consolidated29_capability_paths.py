"""Replay R12 exact pathfixture on SOURCE29 and actual ARC wireless object.

The retained original tool is copied with only module-target and tool-directory
resolution adapted. This proves actual595recordARCobject, not a fullmodule.
"""
import argparse,hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--wireless-object',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/audit_r12_capability_paths.py';text=original.read_text();old="ROOT=Path(__file__).resolve().parents[1]";assert text.count(old)==1;text=text.replace(old,"ROOT=Path("+repr(str(ROOT))+')',1)
 old="candidate=Elf(ROOT/'outputs/rea/consolidated23-beacon-r12-complete-pair-20261022T205500Z-r1/first-joint/wlan/wlan.ko')";assert text.count(old)==1;text=text.replace(old,'candidate=Elf(Path('+repr(str(a.wireless_object.resolve()))+'))',1);script=a.output/'adapted-exact-path-fixture.py';script.write_text(text);env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools');proc=subprocess.run([sys.executable,str(script),'--candidate',str(a.candidate),'--compiler',str(a.compiler),'--output',str(a.output/'actual')],env=env,capture_output=True);(a.output/'run.stderr').write_bytes(proc.stderr);assert not proc.returncode,proc.stderr.decode();r=json.loads((a.output/'actual/result.json').read_text());r['status']='PASS_CONSOLIDATED29_ACTUAL_CAPABILITY_SOURCE_PATH_AND_ARC_PRIVATE_TABLE_OBJECT';r['ARC_table_target']=str(a.wireless_object);r['full_module_qualification']=False;r['adaptation']='Only exactmodulepath→actualARCwirelessobject andROOTresolution; testC/controlblocksunchanged';r['tool_pins']={str(p):sha(p)for p in[Path(__file__),original,script,a.wireless_object]};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in ['status','setter_getter_transactions','actual_frame_block_cases','TLV_cases','ARC_table_target']},indent=2))
if __name__=='__main__':main()
