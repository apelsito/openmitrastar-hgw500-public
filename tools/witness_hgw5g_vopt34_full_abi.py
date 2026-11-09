"""VOPT34 ICtail/old embedding witness from frozen exact ARC tool."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
CHECK=""" old,new=rows
 delta=new['sizes']['ieee80211com']-old['sizes']['ieee80211com']
 assert delta>0
 for typ in ['ieee80211com','ieee80211vap','ieee80211_beacon_offsets','ieee80211_beacon_param_t']:assert old['fields'][typ]==new['fields'][typ],'old fields '+typ
 for m,x in old['fields']['qdrv_wlan'].items():
  y=new['fields']['qdrv_wlan'][m]
  if m=='ic':assert y['offset']==x['offset']and y['size']==x['size']+delta
  else:assert y['size']==x['size']and y['offset']==x['offset']+(delta if x['offset']>=old['fields']['qdrv_wlan']['ic']['offset']+old['fields']['qdrv_wlan']['ic']['size']else 0),m
 assert old['fields']['qdrv_vap']==new['fields']['qdrv_vap']
 for typ,size in old['sizes'].items():assert new['sizes'][typ]==size+(delta if typ in('ieee80211com','qdrv_wlan')else 0),typ
 assert new['extensions']['ieee80211com.om_vopt']==old['sizes']['ieee80211com']
 assert new['extensions']['ieee80211_channel.ic_maxpower_normal']==12
"""
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);original=ROOT/'tools/witness_consolidated23_beacon_r12_abi.py';t=original.read_text();start=t.index("extensions=[('ieee80211com','om_bss_tm_flags')");end=t.index('\n sizes=',start);t=t[:start]+"extensions=[('ieee80211com',n)for n in ['om_vopt','om_vopt482','om_vopt_work','om_vopt_lock','om_vopt_stopping','om_vopt_pending','om_vopt_running','om_vopt_destroying','om_vopt_last_error','om_vopt_vsp_get','om_vopt_vsp_set']]+[('ieee80211_channel','ic_maxpower_normal')]"+t[end:];start=t.index(' old,new=rows');end=t.index(' for path,h in pins.items():',start);t=t[:start]+CHECK+t[end:];t=t.replace('PASS_ARC_CONSOLIDATED23_FULL_PARSED_PREFIX_AND_DECLARED_EMBEDDING_EXTENTS','PASS_ARC_VOPT34_ALL_OLD_PREFIX_IC_TAIL_AND_EMBEDDING_SHIFT').replace("'dependency_pins':len(pins)","'dependency_pins':len(pins),'host_delta':delta");script=a.output/'actual-vopt34-abi-witness.py';script.write_text(t,newline='\n');env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools');r=subprocess.run([sys.executable,str(script),'--parent',str(a.parent),'--candidate',str(a.candidate),'--output',str(a.output/'actual')],capture_output=True,env=env);(a.output/'run.stderr').write_bytes(r.stderr);(a.output/'run.stdout').write_bytes(r.stdout);assert not r.returncode,r.stderr.decode();proof=json.loads((a.output/'actual/result.json').read_text());proof['tool_pins']={str(x):sha(x)for x in[Path(__file__),original,script]};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k]for k in['status','host_delta','old_members_checked','dependency_pins']},indent=2))
if __name__=='__main__':main()
