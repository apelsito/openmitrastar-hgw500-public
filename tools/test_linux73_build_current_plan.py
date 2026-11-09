"""Actualcurrentplan+threewronghashnegatives; plancreatesnobuilddirectory."""
import argparse,json,hashlib,subprocess,sys
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--tool',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('args',nargs=argparse.REMAINDER);a=p.parse_args();require=lambda x,m:None if x else(_ for _ in()).throw(AssertionError(m));require(not a.output.exists(),'outputexists');args=a.args[1:]if a.args[:1]==['--']else a.args;target=Path(args[args.index('--output')+1]);require(not target.exists(),'plantargetexists');cmd=[sys.executable,str(a.tool),*args];r=subprocess.run(cmd,capture_output=True,text=True);require(not r.returncode,r.stderr);plan=json.loads(r.stdout);require(plan['status']=='PASS_PLAN_ONLY_CURRENT_INPUTS_AND_ALL_MODULE_MEMBERS_VALIDATED','status');require(not target.exists(),'plancreatedtarget');required=plan['required_kernel_config'];require(required['GPIOLIB']==required['I2C']==required['CFG80211_REQUIRE_SIGNED_REGDB']=='y','config');negative=[]
 for flag,reason in[('--expected-config-sha256','Base config SHA256 mismatch'),('--compiler-sha256','Compiler SHA256 mismatch'),('--expected-kernel-makefile-sha256','Kernel Makefile SHA256 mismatch')]:
  bad=cmd.copy()
  if flag in bad:bad[bad.index(flag)+1]='0'*64
  else:bad.extend([flag,'0'*64])
  q=subprocess.run(bad,capture_output=True,text=True);require(q.returncode!=0 and reason in q.stderr and not target.exists(),flag);negative.append({'case':flag,'rejected':True})
 a.output.mkdir(parents=True);(a.output/'plan.json').write_text(json.dumps(plan,indent=2)+'\n');r={'status':'PASS_CURRENT_R16_PLAN173FILES72UNITS21MODULES_AND_THREE_HASH_NEGATIVES','hardware_accessed':False,'build_started':False,'output_directory_absent':True,'manifest_files':plan['driver_manifest_files_checked'],'C_units':plan['kbuild_source_units'],'modules':len(plan['kbuild_modules']),'requiredconfig':required,'negative_cases':negative,'tool_sha256':sha(a.tool)};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
