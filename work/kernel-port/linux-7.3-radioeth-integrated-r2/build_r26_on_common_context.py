"""Reuse the qualified R26 source on this thread's paired common kernel.

Never contacts the other chat, edits its sources or accesses hardware.
The original R26 kernel_overlay must match this common source before build.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess
HERE=Path(__file__).resolve().parent
WORKSPACE=Path('/workspace/user-home/Desktop/MitraStar')
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
COMMON=BASE/'radio73-common-r3-context-v1'
R26=WORKSPACE/'outputs/rea/linux73-clear-reset-candidate-20261023T064300Z-r26'
PAIR26=WORKSPACE/'outputs/rea/linux73-clear-reset-r26-pair-receipt-20261023T066500Z-r1/result.json'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 require(not a.output.exists(),'Immutable output exists')
 common=json.loads((COMMON/'result.json').read_text())
 require(common['status']=='PASS_PAIRED_COMMON_KERNEL_REALTEK_ETHERNET_R24_22_NATIVE_ABI','Common pair is not accepted offline')
 require(sha(R26/'result.json')=='877d4adbb9ea3403e1fdec714f1576937e19963e717f79ae443d4060bf0f2e07','R26 receipt drift')
 require(sha(PAIR26)=='eb6d927c378c6a7bc52c1a2ce24b9359f7c4bb9166d496e9a0f72a1698007e75','R26 pair proof drift')
 original=json.loads(PAIR26.read_text())
 require(original['status']=='PASS_PAIRED_REAL_LINUX73_74C_22MODULES_IDENTICAL_TYPED_SRAM','R26 prior pair unqualified')
 os.umask(0o077);a.output.mkdir(mode=0o700)
 snapshot=a.output/'r26-source'
 shutil.copytree(R26,snapshot,ignore=shutil.ignore_patterns('__pycache__'))
 manifest=json.loads((snapshot/'result.json').read_text())
 for relative,pin in manifest['files'].items():require(sha(snapshot/relative.replace('\\','/'))==pin,'R26 input changed')
 tool=WORKSPACE/'tools/build_linux73_sram_native_pair.py'
 tc=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')
 command=['python3',str(tool),'--candidate',str(snapshot),'--kernel-source',str(COMMON/'kernel-source'),'--kernel-context',str(COMMON/'a/kernel'),'--gpl',str(WORKSPACE/'work/sources/Quantenna-GPL'),'--output',str(a.output/'pair'),'--cross-prefix',tc,'--jobs','6']
 print('RUN R26 common native pair',flush=True)
 with (a.output/'pair-build.log').open('xb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
 native=json.loads((a.output/'pair/result.json').read_text())
 require(native['status']=='PASS_PAIRED_REAL_LINUX73_74C_22MODULES_IDENTICAL_TYPED_SRAM','R26/common pair unqualified')
 changed=[]
 for name,data in native['lanes'][0]['modules'].items():
  prior=common['lanes'][0]['modules']['native/'+name]
  if data['sha256']!=prior['sha256']:changed.append(name)
 # Compare source hashes to distinguish semantic deltas from prefix-dependent
 # diagnostic __FILE__ strings. The latter can alter hashes of unchanged modules.
 comparison=[]
 r24=COMMON/'r24-source'
 for relative,pin in manifest['files'].items():
  relative=relative.replace('\\','/')
  if relative.split('/')[0] not in ['source','headers','providers']:continue
  other=r24/relative
  if not other.is_file() or sha(other)!=pin:comparison.append(relative)
 report={'status':'PASS_R26_NATIVE_PAIR_ON_THIS_COMMON_KERNEL','hardware_accessed':False,'firmware_eligible':False,'SRAM_registered':False,'radio5g_started':False,'common_kernel_receipt_sha256':sha(COMMON/'result.json'),'R26_source_result_sha256':sha(snapshot/'result.json'),'R26_original_pair_sha256':sha(PAIR26),'paired_native_receipt_sha256':sha(a.output/'pair/result.json'),'changed_module_hashes_vs_common_R24':changed,'changed_source_files_vs_R24':comparison,'kernel_release':common['release'],'module_count':22,'C_units':74,'limits':['Common kernel ABI already witnessed; new native imports/ISA and pair hashes verified.','Source is R26, not a new SRAM board-admission implementation.','No firmware loading, radio activation, map/bus/reset or traffic proof.','Hardware producer quiescence and normal driver load remain separate gates.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'changed_module_hashes_vs_R24':changed,'changed_source_files':comparison},indent=2))
if __name__=='__main__':main()
