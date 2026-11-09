"""Source30 four realCunits×2 against exactqualifiedcombined29 closure.

Before anyreuse requirecompletecombinedABI, sameheaderlinepositions andall
unchangedsource/header hashes. Reused54units/lane carryreal29sourcebuildpins.
"""
import argparse,hashlib,json,os,shutil
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--first',type=Path,required=True);p.add_argument('--second',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True);p.add_argument('--abi',type=Path,required=True);p.add_argument('--wlan-baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();qual=json.loads(a.qualification.read_text());assert qual['status']=='PASS_OFFLINE_CONSOLIDATED29_RECORDS_SOURCE_MODULE_CHECKPOINT';abi=json.loads(a.abi.read_text());assert abi['status']=='PASS_ARC_CONSOLIDATED30_ALL_COMBINED_OLD_MEMBERS_SIZES_AND_POLICY_PADDING'and abi['host_delta']==0
 def inventory(src):return{str(p.relative_to(src)).replace('\\','/'):sha(p)for p in(src/'source').rglob('*')if p.is_file()and p.suffix in ['.c','.h']}
 old,new=inventory(a.parent_source),inventory(a.candidate);assert set(old)==set(new);changed={k for k in old if old[k]!=new[k]};assert changed=={'source/qdrv/qdrv_wlan.c','source/wlan/ieee80211_input.c','source/wlan/ieee80211_node.c','source/wlan/ieee80211_wireless.c'}
 oldh=(a.parent_source/'headers/net80211/ieee80211_var.h').read_text();newh=(a.candidate/'headers/net80211/ieee80211_var.h').read_text();normalized=newh.replace('\tbool om_coc_pm_pending; u8 om_20_40_bss_coex; /* OEM449: prior padding. */','\tbool om_coc_pm_pending;').replace('void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap); void om_ieee80211_change_bw(struct ieee80211vap *vap,int bw,int delay_ch_switch);','void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap);');assert normalized==oldh and len(newh.splitlines())==len(oldh.splitlines())
 for path in(a.parent_source/'headers').rglob('*'):
  if path.is_file()and path.name!='ieee80211_var.h':assert sha(path)==sha(a.candidate/path.relative_to(a.parent_source))
 pins={}
 for parent in[a.first,a.second]:
  r=json.loads((parent/'result.json').read_text());assert r['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
  for path,h in json.loads((parent/'input-pins.json').read_text()).items():assert sha(path)==h;pins[path]=h
 for directory in[a.parent_source,a.candidate]:
  for root in ['source','headers']:
   for path in(directory/root).rglob('*'):
    if path.is_file():pins[str(path)]=sha(path)
 for path in [Path(__file__),Path(b.__file__),a.qualification,a.abi,a.candidate/'result.json']:pins[str(path)]=sha(path)
 for directory in[a.first,a.second]:
  for path in directory.rglob('*'):
   if path.is_file()and(path.suffix in['.o','.d','.ko']or path.name.endswith('.command.json')or path.name.endswith('.o.cmd')):pins[str(path)]=sha(path)
 for path,h in pins.items():assert sha(path)==h
 canonical={b.key(path)for path in pins};a.output.mkdir(parents=True);(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');q,w,h=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';wnames=json.loads((a.wlan_baseline/'result.json').read_text())['units'];groups=[('qdrv',b.parse_names(q)),('wlan',wnames),*[(c,[n])for c,n in b.PROVIDERS.items()]];rows=[]
 for lane,parent in [('a',a.first),('b',a.second)]:
  for c,names in groups:
   folder=a.output/lane/c;folder.mkdir(parents=True)
   for name in names:
    rel='source/'+('qdrv'if c=='qdrv'else'wlan')+'/'+name+'.c';source=a.candidate/rel;fresh=rel in changed
    if fresh:
     cmd,_=b.compile_command(c,name,folder,q,w,h);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+name));ds=b.readdeps(folder/(name+'.d'));assert not {b.key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-canonical,'unpinned'+name;(folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(source)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n')
    else:
     for ext in ['.o','.d']:shutil.copyfile(parent/c/(name+ext),folder/(name+ext))
     shutil.copyfile(parent/c/('.'+name+'.o.cmd'),folder/('.'+name+'.o.cmd'));command=next(Path(p)for p in pins if p.endswith('/'+c+'/compile-'+name+'.command.json'));shutil.copyfile(command,folder/('compile-'+name+'.command.json'))
    row={'lane':lane,'component':c,'name':name,'source_sha256':sha(source),'object_sha256':sha(folder/(name+'.o')),'fresh':fresh};rows.append(row);print(json.dumps(row),flush=True)
 for c,names in groups:
  for n in names:assert sha(a.output/'a'/c/(n+'.o'))==sha(a.output/'b'/c/(n+'.o'))
 for path,h in pins.items():assert sha(path)==h
 r={'status':'PASS_CONSOLIDATED30_FOUR_REAL_UNITS_PAIRED_EXACT_PARENT_CLOSURE','hardware_accessed':False,'firmware_eligible':False,'candidate':str(a.candidate),'units':rows,'new_compiled_units':8,'reused_units':108,'old_all_member_abi_unchanged':True,'header_lines_preserved':True,'reproducible':True,'pins':len(pins),'limits':'FourchangedCunits2x +54exactsource/headerobjectsperlane; nojoint/global/physicalacceptance.'};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
