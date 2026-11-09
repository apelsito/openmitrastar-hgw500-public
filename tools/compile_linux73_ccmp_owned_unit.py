"""Compile actual full CCMP73 source againstprepared73packetcontext; no shared mutations."""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--kernel',type=Path,required=True);p.add_argument('--context',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);module=a.output/'module';module.mkdir();shutil.copytree(a.candidate/'headers',module/'headers');shutil.copytree(a.candidate/'source/qdrv',module/'source/qdrv');(module/'source/wlan').mkdir();shutil.copyfile(a.candidate/'source/wlan/ieee80211_crypto_ccmp.c',module/'source/wlan/ieee80211_crypto_ccmp.c');shutil.copytree(a.candidate/'providers/include',module/'providers/include');text=(a.candidate/'Kbuild').read_text();text='\n'.join(l for l in text.splitlines()if l.startswith('QTN_GPL :=')or l.startswith('ccflags-y'))+'\nwlan_ccmp-y := source/wlan/ieee80211_crypto_ccmp.o\nobj-m += wlan_ccmp.o\n';(module/'Kbuild').write_text(text+'\n');pins={str(x):sha(x)for x in[a.candidate/'result.json',a.candidate/'Kbuild',a.context/'.config',a.context/'Module.symvers',a.kernel/'include/crypto/aes.h',a.toolchain/'bin/arc-snps-linux-uclibc-gcc',Path(__file__)]}
 for x in module.rglob('*'):
  if x.is_file():pins[str(x)]=sha(x)
 (a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');cmd=['make','-C',str(a.kernel),'O='+str(a.context),'ARCH=arc','CROSS_COMPILE='+str(a.toolchain/'bin/arc-snps-linux-uclibc-'),'M='+str(module),'-j1','source/wlan/ieee80211_crypto_ccmp.o'];r=subprocess.run(cmd,capture_output=True);(a.output/'compile.stdout').write_bytes(r.stdout);(a.output/'compile.stderr').write_bytes(r.stderr);(a.output/'command.json').write_text(json.dumps(cmd,indent=2)+'\n');result={'status':'NO_GO_ACTUAL_LINUX73_FULL_CCMP_UNIT','hardware_accessed':False,'firmware_eligible':False,'compile_exit':r.returncode,'kernel':str(a.kernel),'context':str(a.context),'candidate':str(a.candidate)}
 if not r.returncode:
  obj=module/'source/wlan/ieee80211_crypto_ccmp.o';result.update(status='PASS_ACTUAL_LINUX73_FULL_CCMP_UNIT_WITH_LIBAES_OBJECT_ONLY',object_sha256=sha(obj),object_bytes=obj.stat().st_size)
 else:result['error_excerpt']=r.stderr.decode(errors='replace')[-4000:]
 assert all(sha(p)==h for p,h in pins.items());(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(r.returncode!=0)
if __name__=='__main__':raise SystemExit(main())
