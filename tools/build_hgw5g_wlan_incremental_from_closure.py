"""Compile changedwirelessC twice and link qualifiedfullsourceWLANclosure.

Parentreceipt must prove all58sourceunits×2 and7modules. Candidateheaders and
allunchangedsource units mustmatchtheparentexactly. Reusequalifiedsourcebuilt
objects onlyforunchangedunits, notOEMbinarypatch. No hardware/config/firmware.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from build_hgw5g_typed_header_closure import compile_command,run,readdeps,key
import build_f370_qdrv_module as qb

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-build',type=Path,required=True);p.add_argument('--parent-qualification',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
 parent=json.loads((a.parent_build/'result.json').read_text());qual=json.loads(a.parent_qualification.read_text());assert parent['status']=='PASS_ALL_TYPED_HEADER_MODULES_PENDING_ABI_DELTA'and parent['reproducible']and qual['status']=='PASS_OFFLINE_COMPLETE_TWENTY_TYPED_HEADER_CLOSURE'
 oldsource=Path(parent['candidate']);qsrc=a.candidate/'source/qdrv';wsrc=a.candidate/'source/wlan';headers=a.candidate/'headers'
 # Allactualinputsourceexceptwireless mustbeidentical; nonewheaderwiringclaim.
 for root in('source/qdrv','source/wlan','headers'):
  for path in(oldsource/root).rglob('*'):
   if path.is_file()and path.suffix in('.c','.h')and path.name!='ieee80211_wireless.c':assert sha(path)==sha(a.candidate/path.relative_to(oldsource)),path
 pins=json.loads((a.parent_build/'input-pins.json').read_text());pins.update({str(a.parent_build/'result.json'):sha(a.parent_build/'result.json'),str(a.parent_qualification):sha(a.parent_qualification),str(a.candidate/'result.json'):sha(a.candidate/'result.json'),str(wsrc/'ieee80211_wireless.c'):sha(wsrc/'ieee80211_wireless.c'),str(Path(__file__)):sha(Path(__file__)),str(Path(__file__).parent/'build_hgw5g_typed_header_closure.py'):sha(Path(__file__).parent/'build_hgw5g_typed_header_closure.py')})
 for root in(qsrc,wsrc,headers):pins.update({str(path):sha(path)for path in root.rglob('*')if path.is_file()and path.suffix in('.c','.h')})
 for path,h in pins.items():assert sha(path)==h,'parentdrift '+path
 names=[row['name']for row in parent['units']if row['component']=='wlan'and row['lane']=='a'];assert len(names)==19
 for lane in('a','b'):
  for n in names:pins[str(a.parent_build/lane/'wlan'/(n+'.o'))]=sha(a.parent_build/lane/'wlan'/(n+'.o'))
 canonical={key(x)for x in pins};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='NO_GO_INCREMENTAL_CLOSURE',hardware_accessed=False,firmware_eligible=False,modules=[],parent_build=str(a.parent_build),candidate=str(a.candidate),unchanged_units_reused=18,new_source_unit_compiles=2,header_context_unchanged=True)
 try:
  for lane in('a','b'):
   folder=a.output/lane/'wlan';folder.mkdir(parents=True);cmd,source=compile_command('wlan','ieee80211_wireless',folder,qsrc,wsrc,headers);run(cmd,qb.context.CONTEXT,folder/'compile-changed-source');dependencies=readdeps(folder/'ieee80211_wireless.d');missing={key(Path(x)if x.startswith('/')else qb.context.CONTEXT/x)for x in dependencies}-canonical;assert not missing,'un-pinneddeps '+str(missing)
   for name in names:
    if name!='ieee80211_wireless':shutil.copyfile(a.parent_build/lane/'wlan'/(name+'.o'),folder/(name+'.o'))
    ds=dependencies if name=='ieee80211_wireless'else readdeps(a.parent_build/lane/'wlan'/(name+'.d'))
    (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(wsrc/(name+'.c'))+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n')
   objects=[str(folder/(n+'.o'))for n in names];(folder/'wlan.mod').write_text('\n'.join(objects)+'\n');run([str(qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(folder/'wlan.o'),*objects],folder,folder/'link-relocatable')
   dep=Path('/workspace/user-home/Desktop/MitraStar/outputs/rea/driver5g-ops-20261022-wlan-baseline-r2/dependencies.symvers');run([str(qb.context.CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(dep),'-o',str(folder/'Module.symvers'),str(folder/'wlan.o')],folder,folder/'modpost');cmd,_=compile_command('wlan','wlan.mod',folder,qsrc,wsrc,headers,True);run(cmd,qb.context.CONTEXT,folder/'compile-metadata');run([str(qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(qb.context.CONTEXT/'scripts/module.lds'),'-o',str(folder/'wlan.ko'),str(folder/'wlan.o'),str(folder/'wlan.mod.o')],folder,folder/'link-module');module=folder/'wlan.ko';result['modules'].append(dict(lane=lane,path=str(module),bytes=module.stat().st_size,sha256=sha(module)))
  assert result['modules'][0]['sha256']==result['modules'][1]['sha256']
  for path,h in pins.items():assert sha(path)==h,'inputdrift '+path
  result.update(status='PASS_SOURCE_WLAN_INCREMENTAL_PARENT_CLOSURE_PENDING_DELTA',reproducible=True,inputs_unchanged=True)
 except Exception as ex:result['error']=str(ex)
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(not result['status'].startswith('PASS_'))

if __name__=='__main__':raise SystemExit(main())
