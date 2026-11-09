"""Actualsources/config/TC/referenceexports plan; mutations onlytempconfigcopies."""
import argparse,hashlib,json,subprocess,sys,importlib.util
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();
 for name in('tool','driver-source','kernel-source','kernel-context','reference-symvers','gpl-root','output'):p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--toolchain-prefix',required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);expected_cfg=sha(a.kernel_context/'.config');mk=sha(a.kernel_source/'Makefile');base=[sys.executable,str(a.tool),'--driver-source',str(a.driver_source),'--kernel-source',str(a.kernel_source),'--kernel-context',str(a.kernel_context),'--reference-symvers',str(a.reference_symvers),'--toolchain-prefix',a.toolchain_prefix,'--gpl-root',str(a.gpl_root),'--expected-config-sha256',expected_cfg,'--expected-kernel-makefile-sha256',mk,'--output',str(a.output/'must-not-exist'),'--plan-only'];rows=[]
 r=subprocess.run(base,capture_output=True);(a.output/'valid.stdout').write_bytes(r.stdout);(a.output/'valid.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();plan=json.loads(r.stdout);assert plan['status']=='PASS_PLAN_ONLY_AELITA_SANITIZED_BOOT_AND_ALL_MODULE_MEMBERS_VALIDATED'and not(a.output/'must-not-exist').exists();assert all('dtbs'not in cmd for cmd in plan['commands'])and plan['reference_symvers']==str(a.reference_symvers);rows.append({'case':'actual-valid-plan','passed':True})
 for flag in('--expected-config-sha256','--expected-kernel-makefile-sha256','--compiler-sha256'):
  args=list(base)
  if flag in args:args[args.index(flag)+1]='0'*64
  else:args[2:2]=[flag,'0'*64]
  r=subprocess.run(args,capture_output=True);assert r.returncode and not(a.output/'must-not-exist').exists();rows.append({'case':flag,'rejected':True,'reason':json.loads(r.stderr)['error']})
 spec=importlib.util.spec_from_file_location('actual_aelita_tool',a.tool);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);cfg=(a.kernel_context/'.config').read_text()
 for key in('INITRAMFS_SOURCE','BUILTIN_DTB_NAME'):
  import re
  bad=re.sub(r'^CONFIG_'+key+r'=.*$', 'CONFIG_'+key+'="private-path"',cfg,flags=re.M)
  try:mod.require_sanitized_boot_config(bad)
  except ValueError as ex:rows.append({'case':'boot-config-'+key,'rejected':True,'reason':str(ex)})
  else:raise AssertionError('bootguardmissed '+key)
 for key in plan['required_kernel_config']:
  value=plan['required_kernel_config'][key];bad=cfg
  # Simulate olddefconfig dropping one requiredoption from a completevalidconfig.
  for k,v in plan['required_kernel_config'].items():bad=re.sub(r'(?m)^(?:CONFIG_'+k+r'=.*|# CONFIG_'+k+r' is not set)\n','',bad);bad+=('CONFIG_'+k+'='+v+'\n'if v!='n'else'# CONFIG_'+k+' is not set\n')
  bad=re.sub(r'(?m)^CONFIG_'+key+r'=.*\n','',bad);f=a.output/('dropped-'+key+'.config');f.write_text(bad)
  try:mod.validate_final_kernel_config(f,plan['required_kernel_config'])
  except ValueError as ex:rows.append({'case':'pre-vmlinux-required-'+key,'rejected':True})
  else:raise AssertionError('requiredguardmissed '+key)
 pins={str(p):sha(p)for p in[a.tool,a.driver_source/'result.json',a.driver_source/'Kbuild',a.kernel_source/'Makefile',a.kernel_context/'.config',a.reference_symvers,Path(a.toolchain_prefix+'gcc'),Path(__file__)]};assert sha(a.kernel_context/'.config')==expected_cfg;(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result={'status':'PASS_ACTUAL_AELITA_NO_DTBS_PLAN_AND_CONFIG_HASH_BOOT_REQUIREMENT_NEGATIVES','hardware_accessed':False,'kernel_build_started':False,'plan_output_absent':True,'files_checked':plan['driver_manifest_files_checked'],'C_units':plan['kbuild_source_units'],'module_count':len(plan['kbuild_modules']),'reference_symvers_actual_path':str(a.reference_symvers),'reference_symvers_is_new_context':plan['reference_symvers_is_new_context'],'dtbs_requested':False,'cases':rows,'tool_sha256':sha(a.tool),'predecessor_sha256':sha(a.tool.with_name('linux73_build_current_ipv6.py')),'limits':['Actualplanchecksrealsources/config/compiler/referencekernelexports; notfreshkernel/modulebuild','Required/bootguards areexecutedagainsttemporaryconfigcopies only; nosealed/sourcecontextmutated']};(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
