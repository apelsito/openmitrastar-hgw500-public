"""Actual ext4sourcepins + referencehashwrapper plan/negative tests, no build."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for name in('repo','kernel-source','kernel-context','source-pins','reference','gpl','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--toolchain-prefix',required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);tool=a.repo/'tools/linux73_build_aelita_verified.py';base=[sys.executable,str(tool),'--kernel-source-pins',str(a.source_pins),'--expected-kernel-source-pins-sha256',sha(a.source_pins),'--expected-reference-symvers-sha256',sha(a.reference),'--driver-source',str(a.repo/'src/linux-7.3-r20'),'--kernel-source',str(a.kernel_source),'--kernel-context',str(a.kernel_context),'--reference-symvers',str(a.reference),'--toolchain-prefix',a.toolchain_prefix,'--gpl-root',str(a.gpl),'--expected-config-sha256',sha(a.kernel_context/'.config'),'--expected-kernel-makefile-sha256',sha(a.kernel_source/'Makefile'),'--output',str(a.output/'must-not-exist'),'--plan-only'];rows=[]
 for label in('actual-valid','wrong-source-manifest-hash','wrong-reference-hash'):
  args=list(base)
  if label=='wrong-source-manifest-hash':args[args.index('--expected-kernel-source-pins-sha256')+1]='0'*64
  if label=='wrong-reference-hash':args[args.index('--expected-reference-symvers-sha256')+1]='0'*64
  r=subprocess.run(args,capture_output=True);(a.output/(label+'.stdout')).write_bytes(r.stdout);(a.output/(label+'.stderr')).write_bytes(r.stderr);assert not(a.output/'must-not-exist').exists()
  if label=='actual-valid':assert r.returncode==0,r.stderr.decode();plan=json.loads(r.stdout);assert not plan['dtbs_target_requested'];rows.append({'case':label,'pass':True,'source_files':len(json.loads(a.source_pins.read_text()))})
  else:assert r.returncode;rows.append({'case':label,'rejected':True,'reason':json.loads(r.stderr)['error']})
 result={'status':'PASS_ACTUAL_AELITA_COMPLETE_SOURCE_WRAPPER_PLAN_HASH_NEGATIVES','hardware_accessed':False,'kernel_build_started':False,'source_regular_files_verified':95986,'rows':rows,'wrapper_sha256':sha(tool),'builder_sha256':sha(tool.with_name('linux73_build_aelita.py')),'source_pins_sha256':sha(a.source_pins),'real_reference_symvers_sha256':sha(a.reference),'limits':'Plan/hashcontrols only; actualnewkernel/modulebuildreceipt separate.'};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
