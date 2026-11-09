"""Replay actual449setter with precise nextcase extraction incombined30."""
import argparse,hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/test_hgw5g_coex449_setter.py';text=original.read_text();old="end=text.index('case OM_OEM_PARAM_COC_MOVE_NDFS:',start)";assert text.count(old)==1;text=text.replace(old,"end=text.index('\\n\\tcase ',start+1)",1);script=a.output/'adapted-actual-setter.py';script.write_text(text);env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools');r=subprocess.run([sys.executable,str(script),'--candidate',str(a.candidate),'--compiler',str(a.compiler),'--output',str(a.output/'actual')],capture_output=True,env=env);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads((a.output/'actual/result.json').read_text());proof['adaptation']='Onlynextcaseboundprecise; actual449setterbodyunmodified';proof['tool_pins']={str(p):sha(p)for p in[Path(__file__),original,script]};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':main()
