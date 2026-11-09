"""Build a full reset-v2 module twice against the exact running ETH73 context."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--context',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 assert sha(a.candidate/'driver/qtn-topaz-emac-eth73.c')=='9f49c8a9c6478a18793062d87c051132ea6812a557ea24ae006b50f21e93fd33'
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1792365298',KBUILD_BUILD_TIMESTAMP='@1792365298',KBUILD_BUILD_USER='openmitrastar',KBUILD_BUILD_HOST='eth73',KBUILD_BUILD_VERSION='1')
 exports={l.split()[1] for l in (a.context/'Module.symvers').read_text().splitlines()}
 results=[]
 for lane in ['a','b']:
  module=a.output/lane;shutil.copytree(a.candidate/'driver',module)
  cmd=['make','-C',str(a.source),'O='+str(a.context),'ARCH=arc','CROSS_COMPILE='+tc,'M='+str(module),'KCFLAGS=-ffile-prefix-map='+str(module)+'=/eth73-module','-j6','modules']
  with (a.output/('build-'+lane+'.log')).open('xb') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=300)
  ko=module/'qtn-topaz-emac-eth73.ko';asm=subprocess.check_output([tc+'objdump','-d',str(ko)],text=True)
  assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
  imports=[l.split()[-1] for l in subprocess.check_output([tc+'nm','-u',str(ko)],text=True).splitlines()]
  assert not set(imports)-exports
  results.append({'lane':lane,'sha256':sha(ko),'bytes':ko.stat().st_size,'imports':len(imports),'forbidden_instructions':0})
 assert results[0]['sha256']==results[1]['sha256']
 report={'schema':'openmitrastar.eth73-reset-module/v2','status':'PASS_PAIRED_FULL_MODULE','hardware_accessed':False,'driver_sha256':sha(a.candidate/'driver/qtn-topaz-emac-eth73.c'),'lanes':results,'physical':'UNRUN'}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
