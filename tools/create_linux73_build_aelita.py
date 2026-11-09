"""Create a new exact-derived AELITA builder; predecessor remains byte-exact."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
repo=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
parent=repo/'tools/linux73_build_current_ipv6.py';s=parent.read_text();before=hashlib.sha256(parent.read_bytes()).hexdigest()
s=s.replace('Current portable Linux 7.3 complete driver/providers build. --plan-only is read-only.','Sanitized AELITA Linux7.3 kernel/modules builder; no dtbs target.')
s=s.replace("'RTL8192EE':'m'}","'RTL8192EE':'m','QTN_TOPAZ_ETH73':'y'}",1)
s=s.replace("p.add_argument('--expected-kernel-commit'", "p.add_argument('--reference-symvers',type=Path,help='Explicit existing real kernel Module.symvers used only as input reference when new context is not built yet')\n p.add_argument('--expected-kernel-commit'",1)
needle=" require((c/'Module.symvers').is_file(),'Base Module.symvers required as reference; it will not substitute the new build')";assert s.count(needle)==1
s=s.replace(needle," require_sanitized_boot_config(cfg)\n reference=(a.reference_symvers or c/'Module.symvers').resolve()\n require(reference.is_file(),'Existing real Module.symvers required as reference; supply --reference-symvers or build the new kernel context first')",1)
s=s.replace("c/'Module.symvers',compiler,Path(__file__).resolve()","reference,compiler,Path(__file__).resolve()",1)
s=s.replace("'kernel_DT_privacy_not_audited':True}","'kernel_DT_privacy_not_audited':True,'reference_symvers':str(reference),'reference_symvers_is_new_context':reference==c/'Module.symvers','dtbs_target_requested':False,'input_boot_selection_sanitized':True}",1)
s=s.replace("'vmlinux','dtbs','modules'","'vmlinux','modules'",1)
s=s.replace("changes=r['required_kernel_config']|{'INITRAMFS_SOURCE':'\"\"'}","changes=r['required_kernel_config']|{'INITRAMFS_SOURCE':'\"\"','BUILTIN_DTB_NAME':'\"\"'}",1)
needle="   for i,cmd in enumerate(r['commands']):\n    with(out/f'{i:02d}-build.log').open('xb')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True)";assert s.count(needle)==1
s=s.replace(needle,"   for i,cmd in enumerate(r['commands']):\n    if 'vmlinux'in cmd:\n     validate_final_kernel_config(out/'kernel-context/.config',r['required_kernel_config'])\n    with(out/f'{i:02d}-build.log').open('xb')as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True)\n    if i==0:validate_final_kernel_config(out/'kernel-context/.config',r['required_kernel_config'])",1)
insert='''def require_sanitized_boot_config(cfg):
 require(re.search(r'^CONFIG_INITRAMFS_SOURCE=""$',cfg,re.M),'Sanitized AELITA config must have empty INITRAMFS_SOURCE')
 require(re.search(r'^CONFIG_BUILTIN_DTB_NAME=""$',cfg,re.M),'Sanitized AELITA config must have empty BUILTIN_DTB_NAME')
 # ARC selects the GENERIC_BUILTIN_DTB framework itself. Only the name selects
 # the actual dtb-y list; an empty name remains required after olddefconfig.
def validate_final_kernel_config(path,required):
 cfg=path.read_text();require_sanitized_boot_config(cfg)
 for key,val in required.items():require(re.search(r'^'+re.escape('CONFIG_'+key+'='+val if val!='n'else'# CONFIG_'+key+' is not set')+r'$',cfg,re.M),'Required pre-vmlinux config omitted or changed '+key)
 return cfg
'''
s=s.replace('def arguments():',insert+'\ndef arguments():',1)
s=s.replace('PASS_PLAN_ONLY_CURRENT_INPUTS_AND_ALL_MODULE_MEMBERS_VALIDATED','PASS_PLAN_ONLY_AELITA_SANITIZED_BOOT_AND_ALL_MODULE_MEMBERS_VALIDATED')
s=s.replace('PASS_SINGLE_LINUX73_KERNEL_AND_MODULE_BUILD_PENDING_PAIR_ABI_AND_PHYSICAL_GATES','PASS_SINGLE_SANITIZED_AELITA_KERNEL_MODULE_BUILD_PENDING_PAIR_ABI_PHYSICAL')
target=repo/'tools/linux73_build_aelita.py';assert not target.exists();target.write_text(s,newline='\n');assert hashlib.sha256(parent.read_bytes()).hexdigest()==before
e=ROOT/'outputs/rea/linux73-build-aelita-derivation-20261022T234000Z-r1';e.mkdir(parents=True,exist_ok=False);r={'status':'NEW_DERIVED_TOOL_PREDECESSOR_UNCHANGED_PENDING_ACTUAL_PLAN','predecessor':str(parent),'predecessor_sha256':before,'new_tool':str(target),'new_tool_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'changes':['No dtbs target','Require emptyDTname/initramfs at inspection, afterolddefconfig andprevmlinux','Validateallrequiredconfigafterolddefconfig beforekernelcompile','Explicitexistingrealreference-symvers; nevercopyit tonewbuild','PreserveETH73contract mandatory'],'hardware_accessed':False};(e/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
