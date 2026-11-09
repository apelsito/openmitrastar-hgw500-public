"""Derive minimal32→34 builder gated by fullformerpaddingABI proof."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'tools/build_consolidated32_bounded467_pair.py').read_text()
s=s.replace("p.add_argument('--output',type=Path,required=True);a=", "p.add_argument('--abi',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=",1)
s=s.replace("allowed={'source/wlan/ieee80211_scan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c','headers/net80211/ieee80211_var.h'};seen=set()", "ab=json.loads(a.abi.read_text());assert ab['status']=='PASS_ARC_WEATHER478_ALL_OLD_FIELDS_WIRE_SIZES_FORMER_PADDING22605'and ab['host_delta']==0 and ab['rows'][1]['extensions']['weather478']=={'offset':22605,'size':1}\n for path,h in json.loads((a.abi.parent/'input-pins.json').read_text()).items():assert sha(path)==h;pins[path]=h\n allowed={'source/qdrv/qdrv_wlan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c','headers/net80211/ieee80211_var.h'};seen=set()")
s=s.replace("new.replace(' int om_ieee80211_dfs_channel_available(struct ieee80211com *ic);','')", "new.replace(' u8 om_weather_cac_enabled; /* OEM478: former padding. */','')")
s=s.replace("a.parent_checkpoint/'input-pins.json']", "a.parent_checkpoint/'input-pins.json',a.abi]")
s=s.replace('PASS_CONSOLIDATED32_BOUNDED467_THREE_UNITS_PAIRED_SEVEN_MODULES_PENDING_GLOBAL','PASS_WEATHER478_SOURCE34_THREE_UNITS_PAIRED_SEVEN_MODULES_PENDING_GLOBAL')
t=ROOT/'tools/build_hgw5g_weather478_pair.py';assert not t.exists();t.write_text(s,newline='\n')
