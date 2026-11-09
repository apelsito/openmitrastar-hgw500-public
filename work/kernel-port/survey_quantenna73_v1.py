"""Compile restored 5GHz source units against actual 7.3 headers; no device."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,re,shlex,shutil,subprocess
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
ROOT=Path('/workspace/user-home/Desktop/MitraStar')
REPO=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
CANDIDATE=REPO/'candidates/weather478-source34-20261022T210000Z-r1'
OUT=BASE/'quantenna73-api-survey-v1'
KERNEL=BASE/'radioeth73-events-ram-v2/source'
CONTEXT=BASE/'radioeth73-events-ram-v2/a'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OUT.exists():raise RuntimeError('Immutable survey exists')
 qualified=REPO/'evidence/weather478-qualification-20261023T000100Z-r1/result.json'
 proof=json.loads(qualified.read_text())
 assert proof['status']=='PASS_OFFLINE_WEATHER478_SOURCE34_BOOLEAN_AP_SELECTION_SEVEN_MODULE_CLOSURE'
 OUT.mkdir(mode=0o700)
 for name,source in [('source',CANDIDATE/'source'),('headers',CANDIDATE/'headers'),('compat',REPO/'src/compat/include'),('legacy',REPO/'vendor/legacy-gpl'),('port-context',REPO/'vendor/port-context')]:
  shutil.copytree(source,OUT/name)
 (OUT/'compat/linux').mkdir(exist_ok=True)
 for name in ['openmitrastar_bridge.h','openmitrastar_qtn_skb.h']:
  src=ROOT/'work/kernel-port/linux-5.10/include/linux'/name
  shutil.copyfile(src,OUT/'compat/linux'/name)
 command=shlex.split((CONTEXT/'arch/arc/kernel/.reset.o.cmd').read_text().splitlines()[0].split(' := ',1)[1])
 cut=command.index('-c');base=[x for x in command[:cut] if not x.startswith('-Wp,-MMD,')]
 base+=['-DMODULE','-mlong-calls','-mno-millicode','-I'+str(OUT/'headers'),'-I'+str(OUT/'compat'),'-I'+str(OUT/'source/qdrv'),'-I'+str(OUT/'source/wlan')]
 for directory in ['port-context','port-context/drivers','port-context/include','port-context/drivers/include/shared','port-context/drivers/include/kernel','port-context/common','legacy','legacy/drivers','legacy/include','legacy/common']:
  base+=['-I'+str(OUT/directory)]
 base+=['-include',str(OUT/'compat/openmitrastar_qdrv_compat.h'),'-DQDRV','-DQSCS_ENABLED','-DQTN_BG_SCAN','-DQBMPS_ENABLE','-DCONFIG_ARCH_ARC=1','-DCONFIG_RUBY=1','-DCONFIG_QTN_80211K_SUPPORT','-DQTN_ENABLE_TRACE_BUFFER=0','-DQTN_DEBUG','-DOPENMITRASTAR_QDRV_NO_IPV6_OFFLOAD','-DOPENMITRASTAR_NO_LEGACY_PROC','-DOPENMITRASTAR_QDRV_V89_PAIR=1','-DOPENMITRASTAR_SWITCH_EMAC_PORT=1','-DOPENMITRASTAR_SWITCH_EMAC_NO_PHY=1']
 inputs={str(qualified):sha(qualified),str(CONTEXT/'.config'):sha(CONTEXT/'.config'),str(CONTEXT/'arch/arc/kernel/.reset.o.cmd'):sha(CONTEXT/'arch/arc/kernel/.reset.o.cmd')}
 for folder in ['source','headers','compat','legacy','port-context']:
  inputs.update({str(f):sha(f) for f in (OUT/folder).rglob('*') if f.is_file()})
 (OUT/'input-pins.json').write_text(json.dumps(inputs,indent=2)+'\n')
 (OUT/'compile-base.json').write_text(json.dumps(base,indent=2)+'\n')
 jobs=[]
 for module in ['qdrv','wlan']:
  manifest=json.loads((REPO/'manifests'/('build-'+module+'.json')).read_text())
  for record in manifest['units']:
   src=OUT/'source'/module/Path(record['source']).name
   assert src.is_file(),src
   jobs.append((module,record['name'],src))
 def compile(job):
  module,name,source=job;folder=OUT/'objects'/module;folder.mkdir(parents=True,exist_ok=True)
  cmd=base+(['-DQTN_DYN_CCA=1'] if module=='wlan' else [])+['-DKBUILD_BASENAME="'+name+'"','-DKBUILD_MODNAME="'+module+'"','-c','-o',str(folder/(name+'.o')),str(source)]
  (folder/(name+'.command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
  r=subprocess.run(cmd,cwd=CONTEXT,capture_output=True,text=True,timeout=120)
  (folder/(name+'.stderr')).write_text(r.stderr)
  errors=[line for line in r.stderr.splitlines() if re.search(r'error:|fatal error:',line)]
  result={'module':module,'unit':name,'exit':r.returncode,'errors':errors[:16]}
  if not r.returncode:result.update(bytes=(folder/(name+'.o')).stat().st_size,sha256=sha(folder/(name+'.o')))
  print(json.dumps({'module':module,'unit':name,'compiled':r.returncode==0,'first_error':errors[:1]}),flush=True)
  return result
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(compile,jobs))
 result={'status':'QUANTENNA73_API_SURVEY_ONLY','parent_qualified_records':34,'kernel_release':(CONTEXT/'include/config/kernel.release').read_text().strip(),'rows':rows,'compiled':sum(r['exit']==0 for r in rows),'failed':sum(r['exit']!=0 for r in rows),'units':len(rows),'hardware_accessed':False,'module_link':'UNRUN','firmware_eligible':False,'limits':['Real7.3 compile-only; no synthetic installed module or5GHz runtime claim.','WEXT/kernel providers and typed layout/export closure remain separate.']}
 for file,digest in inputs.items():assert sha(Path(file))==digest,file
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ['status','compiled','failed','units','kernel_release']}))
if __name__=='__main__':main()
