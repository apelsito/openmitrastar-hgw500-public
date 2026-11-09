"""Two fresh current driver/provider builds against a pinned fresh kernel ABI."""
import argparse,datetime,hashlib,json,os,re,shutil,subprocess
from pathlib import Path

def sha(path):
 with path.open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser()
 for n in('candidate','kernel-source','kernel-context','gpl','output'):p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--cross-prefix',required=True);p.add_argument('--jobs',type=int,default=4);a=p.parse_args()
 assert not a.output.exists();a.output.mkdir(parents=True)
 d=a.candidate.resolve();k=a.kernel_source.resolve();c=a.kernel_context.resolve();g=a.gpl.resolve();o=a.output.resolve()
 proof=json.loads((d/'result.json').read_text());pins={str(c/n):sha(c/n)for n in('.config','Module.symvers','include/generated/utsrelease.h')};pins[str(d/'Kbuild')]=sha(d/'Kbuild');pins[str(d/'result.json')]=sha(d/'result.json');pins[str(Path(__file__).resolve())]=sha(Path(__file__).resolve())
 for stored,h in proof['files'].items():
  rel=stored.replace('\\','/');assert sha(d/rel)==h,rel;pins[str(d/rel)]=h
  if rel.startswith('kernel-overlay/'):assert sha(k/rel.removeprefix('kernel-overlay/'))==h,rel
 result={'status':'RUNNING_NATIVE_PAIR','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'input_pins':pins,'old_objects_reused':False,'kernel_rebuilt':False,'kernel_reference':'Fresh verified AELITA Linux7.3 kernel remains pinned ABI input','hardware_accessed':False,'firmware_eligible':False,'lanes':[]}
 try:
  for name in('a','b'):
   lane=o/name;lane.mkdir()
   for n in('source','headers','providers'):shutil.copytree(d/n,lane/n)
   shutil.copyfile(d/'Kbuild',lane/'Kbuild')
   env=os.environ|{'SOURCE_DATE_EPOCH':'1792365298','KBUILD_BUILD_TIMESTAMP':'@1792365298','KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'aelita73','KBUILD_BUILD_VERSION':'1','KCFLAGS':'-ffile-prefix-map='+str(lane)+'=/sram73-driver -fmacro-prefix-map='+str(lane)+'=/sram73-driver'}
   cmd=['make','-C',str(k),'O='+str(c),'M='+str(lane),'ARCH=arc','CROSS_COMPILE='+a.cross_prefix,'QTN_GPL='+str(g),'-j'+str(a.jobs),'modules']
   with(lane/'build.log').open('xb')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,check=True)
   mods=sorted(lane.glob('*.ko'));objs=sorted((lane/'source').rglob('*.o'))+sorted((lane/'providers').rglob('*.o'))
   assert len(mods)==22 and len(objs)==74
   exports={l.split()[1]for f in(c/'Module.symvers',lane/'Module.symvers')for l in f.read_text().splitlines()}
   for module in mods:
    imp={l.split()[-1]for l in subprocess.check_output([a.cross_prefix+'nm','-u',str(module)],text=True).splitlines()};assert not imp-exports,(module,imp-exports)
    asm=subprocess.check_output([a.cross_prefix+'objdump','-d',str(module)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),module
   for stored,h in proof['files'].items():
    rel=stored.replace('\\','/')
    if rel.split('/')[0]in('source','headers','providers'):assert sha(lane/rel)==h,rel
   result['lanes'].append({'name':name,'C_units':len(objs),'modules':{x.name:{'bytes':x.stat().st_size,'sha256':sha(x)}for x in mods},'C_objects':{x.relative_to(lane).as_posix():sha(x)for x in objs},'source_copy_pins_pass':True,'all_imports_resolved':True,'forbidden_ISA':False})
   print('PASS native lane '+name,flush=True)
  assert all(sha(Path(path))==h for path,h in pins.items()),'Inputchanged'
  left,right=result['lanes'];diff=[n for n in left['modules']if left['modules'][n]!=right['modules'][n]];objdiff=[n for n in left['C_objects']if left['C_objects'][n]!=right['C_objects'][n]]
  result.update(status='PASS_PAIRED_REAL_LINUX73_74C_22MODULES_IDENTICAL_TYPED_SRAM'if not diff and not objdiff else'NO_GO_NATIVE_PAIR_HASH_DIFFERENCE',module_mismatches=diff,C_mismatches=objdiff,input_pins_after_pass=True)
 except Exception as error:
  result.update(status='STOP_NATIVE_PAIR',error=str(error));raise
 finally:
  result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(o/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],flush=True)
if __name__=='__main__':main()
