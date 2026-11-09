"""Fresh7.3 source/contextcopy plus selectedrealKbuild ARCunit, offline only."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,log,env):
 print(json.dumps({'step':log.name,'command':cmd}),flush=True)
 with log.open('xb')as f:r=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,timeout=900)
 return r.returncode
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--kernel',type=Path,required=True);p.add_argument('--context',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--unit',default='source/qdrv/qdrv_kernel_compat.o');p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();proof=json.loads((a.candidate/'result.json').read_text());assert sha(a.context/'.config')=='2990fb628241fa6714dd41af73bd77f4e4df44f9b8eec37feda31c749818ef27';assert sha(a.toolchain/'bin/arc-snps-linux-uclibc-gcc')=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263';a.output.mkdir(parents=True);env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1792365298',KBUILD_BUILD_TIMESTAMP='@1792365298',KBUILD_BUILD_USER='openmitrastar',KBUILD_BUILD_HOST='qdrv73',KBUILD_BUILD_VERSION='1');kernel=a.output/'kernel-source';assert not run(['cp','-a','--reflink=auto',str(a.kernel),str(kernel)],a.output/'copy-source.log',env)
 for rel,h in proof['kernel_overlay'].items():src=a.candidate/'kernel-overlay'/rel;assert sha(src)==h;dst=kernel/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 context=a.output/'kernel-context';context.mkdir();shutil.copyfile(a.context/'.config',context/'.config');shutil.copyfile(a.context/'Module.symvers',context/'Module.symvers');module=a.output/'module';shutil.copytree(a.candidate/'source',module/'source');shutil.copytree(a.candidate/'headers',module/'headers');shutil.copyfile(a.candidate/'Kbuild',module/'Kbuild');tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');cmd=['make','-C',str(kernel),'O='+str(context),'ARCH=arc','CROSS_COMPILE='+tc];assert not run([str(kernel/'scripts/config'),'--file',str(context/'.config'),'-e','OPENMITRASTAR_QDRV_COMPAT','-e','WIRELESS_EXT','-e','WEXT_PRIV'],a.output/'config-overlay.log',env);result=dict(status='NO_GO_FIRST_LINUX73_QDRV_UNIT',hardware_accessed=False,firmware_eligible=False,candidate=str(a.candidate),unit=a.unit,old_objects_used=False,kernel_source=str(kernel),context=str(context))
 try:
  assert not run(cmd+['olddefconfig'],a.output/'olddefconfig.log',env);cfg=(context/'.config').read_text();assert all('CONFIG_'+k+'=y'in cfg for k in('ARC_CPU_750D','ARC_MMU_V2','ARC_PAGE_SIZE_8K','PREEMPT_NONE','WIRELESS_EXT','WEXT_CORE','WEXT_PRIV','OPENMITRASTAR_QDRV_COMPAT','CFG80211_REQUIRE_SIGNED_REGDB'));assert not run(cmd+['modules_prepare'],a.output/'modules-prepare.log',env);rc=run(cmd+['M='+str(module),'KCFLAGS=-ffile-prefix-map='+str(module)+'=/qdrv73-source','-j1',a.unit],a.output/'compile-unit.log',env);result.update(config_sha256=sha(context/'.config'),compile_exit=rc)
  if not rc:
   obj=module/a.unit;result.update(status='PASS_FIRST_REAL_LINUX73_QDRV_SOURCE_UNIT_OBJECT_ONLY',object_sha256=sha(obj),object_bytes=obj.stat().st_size)
  else:result['first_error_excerpt']=(a.output/'compile-unit.log').read_text()[-3500:]
 except Exception as e:result['error']=str(e)
 result['base_config_unchanged']=sha(a.context/'.config')==proof['pins'][str(a.context/'.config')];(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(not result['status'].startswith('PASS'))
if __name__=='__main__':raise SystemExit(main())
