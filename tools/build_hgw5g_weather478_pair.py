"""Three minimal467 units twice over qualified32, exact55unit reuse eachlane."""
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import build_hgw5g_typed_header_closure as b
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--parent-source',type=Path,required=True);p.add_argument('--parent-pair',type=Path,required=True);p.add_argument('--parent-checkpoint',type=Path,required=True);p.add_argument('--abi',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();cp=json.loads((a.parent_checkpoint/'result.json').read_text());assert cp['status']=='PASS_OFFLINE_CONSOLIDATED32_SCANNER_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT';pins=json.loads((a.parent_checkpoint/'input-pins.json').read_text())
 for path,h in pins.items():assert sha(path)==h,'parent pin drift '+path
 ab=json.loads(a.abi.read_text());assert ab['status']=='PASS_ARC_WEATHER478_ALL_OLD_FIELDS_WIRE_SIZES_FORMER_PADDING22605'and ab['host_delta']==0 and ab['rows'][1]['extensions']['weather478']=={'offset':22605,'size':1}
 for path,h in json.loads((a.abi.parent/'input-pins.json').read_text()).items():assert sha(path)==h;pins[path]=h
 allowed={'source/qdrv/qdrv_wlan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c','headers/net80211/ieee80211_var.h'};seen=set()
 for f in('source','headers'):
  old={p.relative_to(a.parent_source).as_posix():sha(p)for p in(a.parent_source/f).rglob('*')if p.is_file()};new={p.relative_to(a.candidate).as_posix():sha(p)for p in(a.candidate/f).rglob('*')if p.is_file()};assert set(old)==set(new)
  seen|={rel for rel in old if old[rel]!=new[rel]}
  for rel,h in new.items():pins[str(a.candidate/rel)]=h
 assert seen==allowed
 rel='headers/net80211/ieee80211_var.h';old=(a.parent_source/rel).read_text();new=(a.candidate/rel).read_text();assert new.replace(' u8 om_weather_cac_enabled; /* OEM478: former padding. */','')==old and len(new.splitlines())==len(old.splitlines())
 for p in[Path(__file__),Path(b.__file__),a.candidate/'result.json',a.parent_checkpoint/'result.json',a.parent_checkpoint/'input-pins.json',a.abi]:pins[str(p)]=sha(p)
 q,w,h=a.candidate/'source/qdrv',a.candidate/'source/wlan',a.candidate/'headers';wb=b.qb.ROOT/'outputs/rea/driver5g-ops-20261022-wlan-baseline-r2';qb=b.qb.ROOT/'outputs/rea/arc700-20261021-r2/f370-module-20261021T221200Z-r2';groups=[('qdrv',b.parse_names(q)),('wlan',json.loads((wb/'result.json').read_text())['units']),*[(c,[n])for c,n in b.PROVIDERS.items()]];assert sum(len(n)for c,n in groups)==58;a.output.mkdir(parents=True);rows=[]
 for lane in('a','b'):
  parent=a.parent_pair/(lane+'-joint');wave=a.output/lane;wave.mkdir();wr=[]
  for c,names in groups:
   folder=wave/'a'/c;folder.mkdir(parents=True)
   for n in names:
    src=(q if c=='qdrv'else w)/(n+'.c');fresh=src.relative_to(a.candidate).as_posix()in allowed
    for suffix in('.o','.d'):pins[str(parent/c/(n+suffix))]=sha(parent/c/(n+suffix))
    pins[str(parent/c/('.'+n+'.o.cmd'))]=sha(parent/c/('.'+n+'.o.cmd'))
    if fresh:
     cmd,_=b.compile_command(c,n,folder,q,w,h);b.run(cmd,b.qb.context.CONTEXT,folder/('compile-'+n));ds=b.readdeps(folder/(n+'.d'));canonical={b.key(path)for path in pins};missing={b.key(Path(d)if d.startswith('/')else b.qb.context.CONTEXT/d)for d in ds}-canonical;assert not missing,'unpinned '+n+str(missing);(folder/('.'+n+'.o.cmd')).write_text('source_'+str(folder/(n+'.o'))+' := '+str(src)+'\n\ndeps_'+str(folder/(n+'.o'))+' := \\\n'+''.join('  '+d+' \\\n'for d in ds)+'\n')
    else:
     for ext in('.o','.d'):shutil.copyfile(parent/c/(n+ext),folder/(n+ext))
     shutil.copyfile(parent/c/('.'+n+'.o.cmd'),folder/('.'+n+'.o.cmd'));matches=[Path(p)for p in pins if p.endswith('/'+c+'/compile-'+n+'.command.json')];assert matches,'parent compile command '+n;shutil.copyfile(matches[-1],folder/('compile-'+n+'.command.json'))
    row=dict(lane=lane,component=c,name=n,source_sha256=sha(src),object_sha256=sha(folder/(n+'.o')),fresh=fresh);rows.append(row);wr.append(row);print(json.dumps(row),flush=True)
  assert all(sha(path)==h for path,h in pins.items());(wave/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');(wave/'result.json').write_text(json.dumps(dict(status='NO_GO_TYPED_HEADER_CLOSURE',hardware_accessed=False,firmware_eligible=False,units=wr,error='THREE_FRESH_AND55_QUALIFIED32_EXACT_SOURCE_ABI_OBJECTS_REQUIRE_JOINT'),indent=2)+'\n');b.run([sys.executable,str(Path(__file__).parent/'compose_hgw5g_joint_modules_dedup.py'),'--source-build',str(wave),'--candidate',str(a.candidate),'--lane','a','--qdrv-baseline-build',str(qb),'--wlan-baseline-build',str(wb),'--output',str(a.output/(lane+'-joint'))],b.qb.context.CONTEXT,a.output/(lane+'-compose'))
 a1=json.loads((a.output/'a-joint/result.json').read_text());b1=json.loads((a.output/'b-joint/result.json').read_text());assert a1['status']==b1['status']=='PASS_DEDUP_JOINT_COMPOSITION_ALL_STRONG_IMPORTS'
 for c,_ in groups:assert sha(a.output/'a-joint'/c/(c+'.ko'))==sha(a.output/'b-joint'/c/(c+'.ko'))
 assert len(rows)==116 and sum(r['fresh']for r in rows)==6;assert all(sha(p)==h for p,h in pins.items());(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');r=dict(status='PASS_WEATHER478_SOURCE34_THREE_UNITS_PAIRED_SEVEN_MODULES_PENDING_GLOBAL',hardware_accessed=False,firmware_eligible=False,new_compiled_units=6,exact_parent32_objects_reused=110,reproducible=True,units=rows,modules=a1['modules'],pins=len(pins));(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
