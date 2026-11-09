"""Current37 actual449singlecase; allsignedbool boundaries retained."""
import argparse,hashlib,json,subprocess,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);original=ROOT/'tools/test_hgw5g_coex449_setter.py';text=original.read_text();old="end=text.index('case OM_OEM_PARAM_COC_MOVE_NDFS:',start)";assert old in text;text=text.replace(old,"end=text.index('\\n\\tcase ',start+5)");script=a.output/'adapted449.py';script.write_text(text);r=subprocess.run([sys.executable,str(script),'--candidate',str(a.candidate),'--compiler',str(a.compiler),'--output',str(a.output/'actual')],capture_output=True);(a.output/'stdout').write_bytes(r.stdout);(a.output/'stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();proof=json.loads((a.output/'actual/result.json').read_text());proof['adapter_pins']={str(x):sha(x)for x in[Path(__file__),original,script]};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
if __name__=='__main__':main()
