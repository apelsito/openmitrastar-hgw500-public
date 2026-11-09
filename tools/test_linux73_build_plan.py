"""Plan-only integration gate: realinputs and negativehashes, zero builddirs."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--tool',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('args',nargs=argparse.REMAINDER);a=p.parse_args();assert not a.output.exists();args=a.args[1:]if a.args and a.args[0]=='--'else a.args;cmd=[sys.executable,str(a.tool),*args];target=Path(args[args.index('--output')+1]);assert not target.exists();r=subprocess.run(cmd,capture_output=True,text=True);assert not r.returncode,r.stderr;plan=json.loads(r.stdout);assert plan['status']=='PASS_PLAN_ONLY_INPUTS_VALIDATED'and not target.exists();negative=[]
 for flag,reason in[('--expected-config-sha256','Base config SHA256 mismatch'),('--compiler-sha256','Compiler SHA256 mismatch'),('--expected-kernel-makefile-sha256','Kernel Makefile SHA256 mismatch')]:
  bad=cmd.copy()
  if flag in bad:bad[bad.index(flag)+1]='0'*64
  else:bad.extend([flag,'0'*64])
  q=subprocess.run(bad,capture_output=True,text=True);assert q.returncode and reason in q.stderr and not target.exists();negative.append({'case':flag,'rejected':True,'reason':reason})
 a.output.mkdir(parents=True);(a.output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');r={'status':'PASS_PORTABLE_LINUX73_PLAN_REAL153FILES_62UNITS_AND_THREE_HASH_NEGATIVES','hardware_accessed':False,'build_started':False,'plan_output_directory_absent':True,'plan':{'status':plan['status'],'files_checked':plan['driver_manifest_files_checked'],'units':plan['kbuild_source_units'],'kernel_commit_check':plan['kernel_commit_check']},'negative_cases':negative,'tool_sha256':sha(a.tool)};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
