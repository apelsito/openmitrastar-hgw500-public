"""ARC object-only gate for isolated reconstructed466/468 core; immutable pins."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
import build_hgw5g_typed_header_closure as build
from recover_hgw5g_driver_ops import Elf
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();source=a.candidate/'openmitrastar_rbsdfs_recovered.c';cmd=build.wb.command('ieee80211_wireless',a.output,source);cmd[1:1]=['-I'+str(a.candidate.resolve())];template=build.wb.OLD/'.ieee80211_wireless.o.cmd';paths={Path(__file__),Path(build.__file__),Path(build.wb.__file__),template,build.qb.context.CONTEXT/'.config',Path(str(build.qb.context.TC)+'gcc')};paths.update(x for x in a.candidate.iterdir()if x.is_file())
 for tree in('include/generated','include/config','arch/arc/include/generated'):paths.update(x for x in(build.qb.context.CONTEXT/tree).rglob('*')if x.is_file())
 for row in template.read_text().splitlines()[1:]:
  token=row.strip().removesuffix('\\').strip()
  if not token or token.startswith(('$','deps_','source_'))or':'in token or' 'in token:continue
  token=token.replace('/home/user/mitrastar-linux-5.10.260',str(build.qb.context.KERNEL));path=Path(token)if token.startswith('/')else build.qb.context.CONTEXT/token
  if path.is_file():paths.add(path)
 pins={str(p):sha(p)for p in paths};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='NO_GO_ARC_RBSDFS_CORE',hardware_accessed=False,firmware_eligible=False,module_built=False)
 try:
  proc=subprocess.run(cmd,cwd=build.qb.context.CONTEXT,capture_output=True,timeout=180);(a.output/'compile.stderr').write_bytes(proc.stderr);(a.output/'compile.command.json').write_text(json.dumps(cmd,indent=2)+'\n');assert not proc.returncode,proc.stderr.decode()[-2000:]
  deps=(a.output/'ieee80211_wireless.d').read_text().split(':',1)[1].replace('\\\n',' ').split();known={os.path.abspath(p)for p in pins};missing={os.path.abspath(Path(p)if p.startswith('/')else build.qb.context.CONTEXT/p)for p in deps}-known;assert not missing,repr(missing);obj=a.output/'ieee80211_wireless.o';elf=Elf(obj);functions={s['name']for s in elf.syms if s['type']==2 and s['size']};expected={'om_rbsdfs_init','om_rbsdfs_set466','om_rbsdfs_get466','om_rbsdfs_set468','om_rbsdfs_get468','om_rbsdfs_oem_radar_window','om_rbsdfs_oem_mbs_window','om_rbsdfs_oem_send_permitted','om_rbsdfs_oem_expire','om_rbsdfs_exact_frame_window'};assert expected<=functions,repr(functions);assert functions-expected<={'bus_to_virt','muc_to_nocache','nocache_to_muc'},repr(functions)
  for path,h in pins.items():assert sha(path)==h
  result.update(status='PASS_ARC_RBSDFS_ISOLATED_TEN_FUNCTION_CORE_OBJECT_ONLY',input_pins=len(pins),inputs_unchanged=True,bytes=obj.stat().st_size,sha256=sha(obj),functions=sorted(functions),limits='StandaloneARC object only, no kernelregistration/providers/moduleclosure/physicalgrant.')
 except Exception as e:result['error']=str(e)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return int(not result['status'].startswith('PASS'))
if __name__=='__main__':raise SystemExit(main())
