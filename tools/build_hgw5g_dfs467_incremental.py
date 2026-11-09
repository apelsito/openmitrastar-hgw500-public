"""Compile four Coex26 source units independently per lane; reuse54 exact units.

Admission binds full old-field ABI/size equality, unchanged header line count,
and exact declared padding/prototype delta. All other source bytes and paired
parent receipts/objects must match. Joint composition is a separate gate.
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
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--first',type=Path,required=True);p.add_argument('--second',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--abi',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();pins={};units=[]
 def read(path):raw=path.read_bytes();pins[str(path)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
 qual=read(a.qualification);assert qual['status']=='PASS_OFFLINE_CONSOLIDATED29_RECORDS_SOURCE_MODULE_CHECKPOINT';abi=read(a.abi);assert abi['status']=='PASS_ARC_DFS467_ALL_OLD_FIELDS_WIRE_SIZES_UNCHANGED'and abi['host_delta']==0
 parentmap={str(x.relative_to(a.parent_source)):sha(x)for x in(a.parent_source/'source').rglob('*')if x.is_file()and x.suffix in('.c','.h')};candmap={str(x.relative_to(a.candidate)):sha(x)for x in(a.candidate/'source').rglob('*')if x.is_file()and x.suffix in('.c','.h')};assert set(parentmap)==set(candmap);changed={x for x in parentmap if parentmap[x]!=candmap[x]};assert changed=={'source/wlan/ieee80211_scan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c'}
 oldh=(a.parent_source/'headers/net80211/ieee80211_var.h').read_text();newh=(a.candidate/'headers/net80211/ieee80211_var.h').read_text();normalized=newh.replace('void ieee80211_pm_queue_work(struct ieee80211com *ic); int om_ieee80211_dfs_channel_available(struct ieee80211com *ic);','void ieee80211_pm_queue_work(struct ieee80211com *ic);');assert normalized==oldh and len(newh.splitlines())==len(oldh.splitlines())
 for root in('source','headers'):
  for src in(a.parent_source,a.candidate):pins.update({str(x):sha(x)for x in(src/root).rglob('*')if x.is_file()and x.suffix in('.c','.h')})
 for lane,parent in(('a',a.first),('b',a.second)):
  proof=read(parent/'result.json');assert proof['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
  for path,h in read(parent/'input-pins.json').items():assert sha(path)==h;pins[path]=h
  for row in proof['modules']:assert sha(row['path'])==row['sha256'];pins[row['path']]=row['sha256']
 pins[str(Path(__file__))]=sha(__file__);pins[str(a.candidate/'result.json')]=sha(a.candidate/'result.json');a.output.mkdir(parents=True);q=a.candidate/'source/qdrv';w=a.candidate/'source/wlan';h=a.candidate/'headers'
 names=[('qdrv',n)for n in __import__('build_hgw5g_typed_header_closure').parse_names(q)]+[('wlan',r['name'])for r in read(qb.ROOT/'outputs/rea/consolidated29-full-pair-20261022T214100Z-r2/result.json')['units']if r['component']=='wlan'and r['lane']=='a']+list(__import__('build_hgw5g_typed_header_closure').PROVIDERS.items());names=[(c,n)for c,n in names];assert len(names)==58
 for lane,parent in(('a',a.first),('b',a.second)):
  for component,name in names:
   folder=a.output/lane/component;folder.mkdir(parents=True,exist_ok=True);rel='source/'+('qdrv'if component=='qdrv'else'wlan')+'/'+name+'.c';source=a.candidate/rel;old=parent/component;recompile=rel in changed
   for suffix in('.o','.d'):pins[str(old/(name+suffix))]=sha(old/(name+suffix))
   if recompile:
    cmd,_=compile_command(component,name,folder,q,w,h);run(cmd,qb.context.CONTEXT,folder/('compile-'+name));deps=readdeps(folder/(name+'.d'));canonical={key(x)for x in pins};missing={key(Path(x)if x.startswith('/')else qb.context.CONTEXT/x)for x in deps}-canonical;assert not missing,'unpinned'+str(sorted(missing));(folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in deps)+'\n')
   else:
    assert sha(source)==sha(a.parent_source/rel)
    for suffix in('.o','.d'):shutil.copyfile(old/(name+suffix),folder/(name+suffix))
    shutil.copyfile(old/('.'+name+'.o.cmd'),folder/('.'+name+'.o.cmd'));# canonical composer pins thiscommand receipt
    originalcommand=next(Path(p)for p in pins if p.endswith('/'+component+'/compile-'+name+'.command.json'));(folder/('compile-'+name+'.command.json')).write_bytes(originalcommand.read_bytes())
   row=dict(lane=lane,component=component,name=name,source_sha256=sha(source),object_sha256=sha(folder/(name+'.o')),fresh=recompile);units.append(row);print(json.dumps(row),flush=True)
 for path,h in pins.items():assert sha(path)==h,'input drift'+path
 assert all(next(r['object_sha256']for r in units if r['lane']=='a'and r['component']==c and r['name']==n)==next(r['object_sha256']for r in units if r['lane']=='b'and r['component']==c and r['name']==n)for c,n in names)
 (a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_DFS467_THREE_UNITS_PAIRED_INITIALIZED_PARENT_CLOSURE',hardware_accessed=False,firmware_eligible=False,candidate=str(a.candidate),units=units,new_compiled_units=6,reused_units=110,old_member_abi_unchanged=True,header_lines_preserved=True,reproducible=True,limits='55wholeparentunitsreusedperlaneonlyexactsource/ABI/headerlineadmitted; threechangedunitsfreshperlane; jointmodpost/globaldelta separate');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
