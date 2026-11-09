"""Derive a padding-byte witness without changing frozen SOURCE25 ABI tool."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('witness_hgw5g_coc25_full_abi.py');out=src.with_name('witness_hgw5g_coex26_full_abi.py');assert not out.exists();s=src.read_text();s=s.replace('om_coc25_full_layout','om_coex26_full_layout').replace('assert delta in(20,24)','assert delta==0')
 old="if label=='new':expressions+=['offsetof(struct ieee80211com,'+n+')'for n in ['om_coc_move_ndfs','om_coc_last_switch','om_coc_pm_trigger','om_coc_queue_lock','om_coc_stopping','om_coc_completion_pending','om_coc_pm_pending','om_coc_completed_level']]";new="if label=='new':expressions+=['offsetof(struct ieee80211com,om_20_40_bss_coex)','sizeof(((struct ieee80211com*)0)->om_20_40_bss_coex)']";assert old in s;s=s.replace(old,new).replace("extensions=list(v[-8:])if label=='new'else[]","extensions=list(v[-2:])if label=='new'else[]")
 old="assert new['extensions'][:3]==[old['sizes']['ieee80211com']+4*i for i in range(3)]\n assert all(new['extensions'][i]<=new['extensions'][i+1]for i in range(7))";new="assert new['extensions']==[old['fields']['ieee80211com']['om_coc_pm_pending']['offset']+1,1]\n assert new['extensions'][0]+1==old['fields']['ieee80211com']['om_coc_completed_level']['offset']";assert old in s;s=s.replace(old,new).replace('PASS_ARC_COC25_ALL_PARSED_IC_VAP_PREFIX_QDRV_DELTA_WIRE','PASS_ARC_COEX26_ALL_OLD_FIELDS_WIRE_SIZES_PADDING_BYTE');out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
