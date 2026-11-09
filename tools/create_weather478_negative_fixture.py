"""Derive parsedthree-componenttamperfixture; noartifactbytesmodified."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'tools/test_hgw5g_dfs467_negative.py').read_text().replace('audit_hgw5g_dfs467_modules','audit_hgw5g_weather478_modules')
s=s.replace("for c in('wlan','wlan_scan_ap'):","for c in('qdrv','wlan','wlan_scan_ap'):")
s=s.replace("else('function','data','relocation','symbol')","else(('function','anonymous','data','relocation','symbol','diagnostic')if c=='qdrv'else('function','data','relocation','symbol'))")
s=s.replace("name='ieee80211_setmode'if c=='wlan'else'ap_start'","name='ieee80211_setmode'if c=='wlan'else('qdrv_tx'if c=='qdrv'else'ap_start')")
s=s.replace("else:s=next(s for s in e.syms if s['name']=='ieee80211_param_from_qdrv'and s['type']==2);byte('.text',s['value']+116)","else:s=next(s for s in e.syms if s['name']==('qdrv_wlan_exit'if c=='qdrv'else'ieee80211_param_from_qdrv')and s['type']==2);byte('.text',s['value']+116)")
s=s.replace("len(rows)==10","len(rows)==16").replace("cases=10","cases=16").replace('PASS_TEN_DFS467_PARSED_NEGATIVE_DELTA_CASES','PASS_SIXTEEN_WEATHER478_PARSED_NEGATIVE_DELTA_CASES')
t=ROOT/'tools/test_hgw5g_weather478_negative.py';assert not t.exists();t.write_text(s,newline='\n')
