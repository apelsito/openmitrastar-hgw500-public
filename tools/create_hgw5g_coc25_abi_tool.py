"""Create a dedicated ABI witness without modifying the frozen SOURCE23 tool."""
from pathlib import Path

def main():
 target=Path(__file__).with_name('witness_hgw5g_coc25_full_abi.py');assert not target.exists();s=Path(__file__).with_name('witness_hgw5g_legacy23_full_abi.py').read_text()
 replacements=[
 ('SOURCE23 appends two host integers only.','SOURCE25 appends CoC host policy and synchronized worker state only.'),
 ('om_legacy23_full_layout','om_coc25_full_layout'),
 ("if label=='new':expressions+=['offsetof(struct ieee80211com,om_legacy_rate_saved_mode)','offsetof(struct ieee80211com,om_legacy_rate_fixed)']","if label=='new':expressions+=['offsetof(struct ieee80211com,'+n+')'for n in ['om_coc_move_ndfs','om_coc_last_switch','om_coc_pm_trigger','om_coc_queue_lock','om_coc_stopping','om_coc_completion_pending','om_coc_pm_pending','om_coc_completed_level']]"),
 ("extensions=list(v[-2:])if label=='new'else[]","extensions=list(v[-8:])if label=='new'else[]"),
 (' old,new=rows',' old,new=rows\n delta=new["sizes"]["ieee80211com"]-old["sizes"]["ieee80211com"]\n assert delta in(20,24)'),
 ("x['size']+8","x['size']+delta"),
 ("(8 if x['offset']>=old['sizes']['ieee80211com']else 0)","(delta if x['offset']>=old['sizes']['ieee80211com']else 0)"),
 ("old['sizes']['ieee80211com']+8","old['sizes']['ieee80211com']+delta"),
 ("old['sizes']['qdrv_wlan']+8","old['sizes']['qdrv_wlan']+delta"),
 ("assert new['extensions']==[old['sizes']['ieee80211com'],old['sizes']['ieee80211com']+4]","assert new['extensions'][:3]==[old['sizes']['ieee80211com']+4*i for i in range(3)]\n assert all(new['extensions'][i]<=new['extensions'][i+1]for i in range(7))"),
 ('PASS_ARC_LEGACY23_ALL_PARSED_IC_VAP_PREFIX_QDRV_SHIFT8_WIRE','PASS_ARC_COC25_ALL_PARSED_IC_VAP_PREFIX_QDRV_DELTA_WIRE'),
 ("old_members_checked={typ:len(old['fields'][typ])for typ in names},","host_delta=delta,old_members_checked={typ:len(old['fields'][typ])for typ in names},")]
 for old,new in replacements:
  assert old in s,old;s=s.replace(old,new)
 target.write_text(s,newline='\n');print(target)

if __name__=='__main__':main()
