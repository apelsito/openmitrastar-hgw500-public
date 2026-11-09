"""SeparateproviderKbuild avoids duplicate module_init aliases, current73source only."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);shutil.copytree(a.candidate/'source',a.output/'source');shutil.copytree(a.candidate/'headers',a.output/'headers');shutil.copytree(a.candidate/'providers',a.output/'providers');lines=[l for l in(a.candidate/'Kbuild').read_text().splitlines()if l.startswith('QTN_GPL :=')or l.startswith('ccflags-y')];names=['qtn_pm_qos_compat','qtn_platform_support','board_compat','runtime_compat'];lines+=['qtn73_'+n+'-y := providers/'+n+'.o'for n in names]+['obj-m += '+' '.join('qtn73_'+n+'.o'for n in names)];(a.output/'Kbuild').write_text('\n'.join(lines)+'\n');r={'status':'SOURCE_ONLY_SEPARATE_LINUX73_PROVIDER_KBUILD_PENDING_BUILD','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'pins':{str(x):sha(x)for x in[a.candidate/'result.json',a.candidate/'Kbuild',Path(__file__)]},'separate_modules':names};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
