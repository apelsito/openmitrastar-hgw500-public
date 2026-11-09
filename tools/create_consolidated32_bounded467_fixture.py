"""Derive wholeAP/query fixture adding actual461 predicates, never fake461pick."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/'tools/test_hgw5g_dfs467_refreshed_pick.py').read_text()
src=src.replace("query=extract(s,s.index('int om_ieee80211_dfs_channel_available('));metric=", "query=extract(s,s.index('int om_ieee80211_dfs_channel_available('));kp=a.candidate/'source/wlan/openmitrastar_chanset_kernel.inc';kt=kp.read_text();allowed=extract(kt,kt.index('int om_chanset_kernel_allowed('));active=extract(kt,kt.index('int om_chanset_kernel_active('));metric=",1)
needle="'''+metric+'\\n'+startfn+'\\n'+pickfn+'\\n'+wrapper+'\\n'+query+r'''"
assert src.count(needle)==1
extra=r'''
#define IEEE80211_MODE_11B 2
#define IEEE80211_MODE_11NG 8
#define IEEE80211_MODE_11NG_HT40PM 9
struct scan_state {struct ieee80211_scan_state base;unsigned om_chanset_stopping;struct {unsigned active;}om_chanset;};
#define SCAN_PRIVATE(x) ((struct scan_state*)(x))
/* The real allowed predicate rejects every supported467 5GHz mode before
 * active/pick is reached. This explicit trap does not emulate461algorithm. */
static struct ieee80211_channel*om_chanset_kernel_pick(struct ieee80211com*ic){assert(!"5GHz bounded467 must never enter461 picker");return NULL;}
'''
src=src.replace(needle,extra+"'''+allowed+'\\n'+active+'\\n'+metric+'\\n'+startfn+'\\n'+pickfn+'\\n'+wrapper+'\\n'+query+r'''",1)
src=src.replace("str(ap):sha(ap),str(a.compiler)","str(ap):sha(ap),str(kp):sha(kp),str(a.compiler)",1)
src=src.replace("'ap_start':hashlib", "'actual461_allowed':hashlib.sha256(allowed.encode()).hexdigest(),'actual461_active':hashlib.sha256(active.encode()).hexdigest(),'ap_start':hashlib",1)
src=src.replace('PASS_ACTUAL_DFS467_QUERY_REFRESH_WHOLE_APSTART_AP_PICK_5GHZ_FIXTURE','PASS_ACTUAL_CONSOLIDATED32_BOUNDED467_WHOLE_APSTART_PICK_WITH_REAL461_PREDICATES')
target=ROOT/'tools/test_consolidated32_bounded467_refreshed_pick.py';assert not target.exists();target.write_text(src,newline='\n')
