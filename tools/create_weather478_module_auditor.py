"""Strict32→34 completeQDRV/WLAN/AP moduleaudit scoped478sourcechanges."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'tools/audit_consolidated32_bounded467_modules.py').read_text()
s=s.replace("CHANGED={'wlan':{'ieee80211_ioctl_getparam'},'wlan_scan_ap':{'ap_pick_channel'}}","CHANGED={'qdrv':{'qdrv_wlan_init'},'wlan':{'ieee80211_ioctl_getparam','ieee80211_ioctl_setparam'},'wlan_scan_ap':{'ap_pick_channel'}}")
s=s.replace("NEW={'wlan':{'om_ieee80211_dfs_channel_available'},'wlan_scan_ap':set()}","NEW={'qdrv':set(),'wlan':set(),'wlan_scan_ap':set()}")
s=s.replace("EXPORTS={'om_ieee80211_dfs_channel_available'}","EXPORTS=set()")
s=s.replace("DIAG={'ieee80211_delete_wlanunit':[(44,'9653','9d53'),(116,'9753','9e53')],'ieee80211_ioctl_giwfreq':[(76,'180e','580e')],'ieee80211_param_from_qdrv':[(92,'970d','980d')],'ieee80211_ioctl_setparam':[(12752,'f833','f933')],'ap_end':[(104,'ce0a','0e0c')]}","DIAG={'ieee80211_delete_wlanunit':[(44,'9653','a153'),(116,'9753','a253')],'ieee80211_ioctl_giwfreq':[(76,'180e','580e')],'ieee80211_param_from_qdrv':[(92,'970d','980d')],'qdrv_wlan_exit':[(962,'0000','0000')],'ap_end':[(104,'ce0a','0000')]}")
s=s.replace("assert set(diagnostics)==({k for k in DIAG if k!='ap_end'}if component=='wlan'else{'ap_end'})","assert set(diagnostics)==({'ieee80211_delete_wlanunit','ieee80211_ioctl_giwfreq','ieee80211_param_from_qdrv'}if component=='wlan'else({'ap_end'}if component=='wlan_scan_ap'else{'qdrv_wlan_exit'}))")
s=s.replace("expected=2 if sec=='.text'else 0","expected=0 if sec!='.text'else(0 if component=='qdrv'else 0)")
s=s.replace("table_new['size']==599*24","table_new['size']==600*24")
s=s.replace("value-=24","value-=48")
s=s.replace("y[cut+24:]","y[cut+48:]")
s=s.replace("==599;","==600;")
s=s.replace("if component=='wlan_scan_ap':pass","if component in('wlan_scan_ap','qdrv'):pass")
s=s.replace("choices=['wlan_scan_ap','wlan']","choices=['qdrv','wlan_scan_ap','wlan']")
s=s.replace('PASS_COMPLETE_DFS467_BOUNDED_RESIDUAL_MODULE_SCOPE','PASS_COMPLETE_WEATHER478_SOURCE34_RESIDUAL_MODULE_SCOPE')
t=ROOT/'tools/audit_hgw5g_weather478_modules.py';assert not t.exists();t.write_text(s,newline='\n')
