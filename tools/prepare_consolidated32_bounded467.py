"""Minimal qualified32 + bounded467 delta; preserve all461 sources/hooks."""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path
from test_hgw5g_dfs467_refreshed_pick import extract
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--bounded',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 for f in('source','headers'):shutil.copytree(a.parent/f,a.output/f)
 patch=[];changes={}
 def change(rel,new):
  path=a.output/rel;old=path.read_text();path.write_text(new,newline='\n');changes[rel]=sha(path);patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 rel='headers/net80211/ieee80211_var.h';old=(a.output/rel).read_text();needle='void ieee80211_pm_queue_work(struct ieee80211com *ic);';assert old.count(needle)==1;new=old.replace(needle,needle+' int om_ieee80211_dfs_channel_available(struct ieee80211com *ic);',1);assert len(old.splitlines())==len(new.splitlines());change(rel,new)
 rel='source/wlan/ieee80211_scan.c';old=(a.output/rel).read_text();src=(a.bounded/rel).read_text();start=src.index('/* OEM467:');end=src.index('int ieee80211_get_type_of_neighborhood(',start);helper=src[start:end];assert 'if(!ss->ss_last||ss->ss_last>IEEE80211_SCAN_MAX)'in helper;needle='int ieee80211_get_type_of_neighborhood(';assert old.count(needle)==1;change(rel,old.replace(needle,helper+needle,1))
 rel='source/wlan/ieee80211_scan_ap.c';old=(a.output/rel).read_text();src=(a.bounded/rel).read_text();start=src.index('\t\t/* Exact OEM467 selector');end=src.index('\t\t/* IEEE80211_SCAN_PICK_NOT_AVAILABLE_DFS_ONLY',start);delta=src[start:end];needle='\t\t/* IEEE80211_SCAN_PICK_NOT_AVAILABLE_DFS_ONLY';assert old.count(needle)==1;change(rel,old.replace(needle,delta+needle,1))
 rel='source/wlan/ieee80211_wireless.c';old=(a.output/rel).read_text();needle='#define OM_OEM_PARAM_COC_MOVE_NDFS 491';assert old.count(needle)==1;new=old.replace(needle,'#define OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE 467\n'+needle,1);start=new.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=new.index('{',new.index('switch (param[0] & 0xffff)',start));new=new[:brace+1]+'\n\tcase OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE:\n\t\tparam[0]=om_ieee80211_dfs_channel_available(ic);\n\t\treturn 0;\n'+new[brace+1:];start=new.index('static const struct iw_priv_args ieee80211_priv_args[]');end=new.index('\n};',start);new=new[:end]+'\n\t{ OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE,0,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,"dfs_chan_avail" },'+new[end:];change(rel,new)
 for f in('source','headers'):
  for path in(a.parent/f).rglob('*'):
   if path.is_file():
    rel=path.relative_to(a.parent).as_posix()
    if rel not in changes:assert sha(path)==sha(a.output/rel)
 qs=(a.output/'source/wlan/ieee80211_scan.c').read_text();bs=(a.bounded/'source/wlan/ieee80211_scan.c').read_text();q=extract(qs,qs.index('int om_ieee80211_dfs_channel_available('));b=extract(bs,bs.index('int om_ieee80211_dfs_channel_available('));assert q==b
 proof=json.loads((a.bounded/'result.json').read_text());result=dict(status='SOURCE_CONSOLIDATED32_PLUS_BOUNDED467_PENDING_GATES',hardware_accessed=False,firmware_eligible=False,parent=str(a.parent),bounded=str(a.bounded),parent_sha256=sha(a.parent/'result.json'),bounded_sha256=sha(a.bounded/'result.json'),complete_original_records=32,bounded_extra_records=1,allmode_oem467_recovery=False,private_table_records=599,changed_sources=changes,host_layout_changed=False,header_old_line_positions_preserved=True,all_other_sources_exact=True,helper_exact_bounded_r2=True,limits=proof['limits'],safety_deviations=proof['safety_deviations'])
 (a.output/'integration.patch').write_text(''.join(patch));(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
