"""Rebuild7.3 context+providers and identify exact final closure gaps offline."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,re,shutil,subprocess,os
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OLD=BASE/'quantenna73-api-survey-v5';OUT=BASE/'quantenna73-providers-v6'
ROOT=Path('/workspace/user-home/Desktop/MitraStar')
REPO=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
TC=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,name,env=None):
 print('RUN '+name,flush=True)
 with (OUT/name).open('xb') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def main():
 if OUT.exists():raise RuntimeError('Immutable output exists')
 OUT.mkdir(mode=0o700)
 for folder in ['source','headers','compat','legacy','port-context']:shutil.copytree(OLD/folder,OUT/folder)
 shutil.copytree(REPO/'src/platform',OUT/'platform')
 for source in (OUT/'platform').rglob('*.c'):
  t=source.read_text()
  t=re.sub(r'\bstrncpy\(', 'om73_fixed_strncpy(',t)
  t=re.sub(r'\bstrlcpy\(', 'strscpy(',t)
  for name in ['ippkt_dropped','ippkt_check']:t=re.sub(r'\btrace_'+name+r'\(', 'trace_'+name+'_tp(',t)
  source.write_text(t)
 kernel=OUT/'kernel';context=OUT/'kernel-context'
 run(['cp','-a','--reflink=auto',str(OLD/'kernel'),str(kernel)],'copy-kernel.log')
 run(['cp','-a','--reflink=auto',str(OLD/'kernel-context'),str(context)],'copy-context.log')
 env=os.environ|{'SOURCE_DATE_EPOCH':'1792365298','KBUILD_BUILD_TIMESTAMP':'@1792365298','KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73','KBUILD_BUILD_VERSION':'1'}
 make=['make','-C',str(kernel),'O='+str(context),'ARCH=arc','CROSS_COMPILE='+TC]
 run(make+['KCFLAGS=-ffile-prefix-map='+str(context)+'=/quantenna73-context','-j6','vmlinux','dtbs','modules'],'kernel-modules-build.log',env)
 base=[x.replace(str(OLD),str(OUT)) for x in json.loads((OLD/'compile-base.json').read_text())]
 base+=['-DCONFIG_TOPAZ=1','-I'+str(OUT/'platform/ruby')]
 jobs=[]
 for folder,names in [
  ('ruby',['board_compat','runtime_compat','qtn_platform_support','qtn_pm_qos_compat','gpio','iputil','dmautil','emac_lib']),
  ('topaz',['hbm','temp_sens','topaz_congest_queue','switch_tqe','switch_vlan','fwt_if','dpi','switch_emac'])]:
  jobs.extend((folder,name,OUT/'platform'/folder/(name+'.c')) for name in names)
 ancillary=['wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth']
 source_names=['ieee80211_scan_ap','ieee80211_scan_sta','ieee80211_crypto_ccmp','ieee80211_crypto_tkip','ieee80211_xauth']
 jobs.extend(('wlan',name,OUT/'source/wlan'/(source+'.c')) for name,source in zip(ancillary,source_names))
 def compile(job):
  folder,name,source=job;target=OUT/'objects'/folder;target.mkdir(parents=True,exist_ok=True)
  cmd=base+(['-DQTN_DYN_CCA=1'] if folder=='wlan' else [])+['-DKBUILD_BASENAME="'+name+'"','-DKBUILD_MODNAME="'+name+'"','-c','-o',str(target/(name+'.o')),str(source)]
  (target/(name+'.command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  r=subprocess.run(cmd,cwd=context,capture_output=True,text=True,timeout=120);(target/(name+'.stderr')).write_text(r.stderr)
  errors=[l for l in r.stderr.splitlines() if re.search('error:|fatal error:',l)]
  row={'folder':folder,'module':name,'exit':r.returncode,'errors':errors[:24]}
  if not r.returncode:row.update(bytes=(target/(name+'.o')).stat().st_size,sha256=sha(target/(name+'.o')))
  print(json.dumps({'module':name,'compiled':r.returncode==0,'first_error':errors[:1]}),flush=True)
  return row
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(compile,jobs))
 result={'status':'QUANTENNA73_PROVIDER_COMPILE_SURVEY','compiled':sum(r['exit']==0 for r in rows),'failed':sum(r['exit']!=0 for r in rows),'rows':rows,'hardware_accessed':False,'firmware_eligible':False,'kernel_config_sha256':sha(context/'.config'),'kernel_vmlinux_sha256':sha(context/'vmlinux'),'kernel_symvers_sha256':sha(context/'Module.symvers'),'radio_modules_rebuilt':True,'semantic_fixtures':'UNRUN','module_closure':'PENDING'}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['status','compiled','failed']}))
if __name__=='__main__':main()
