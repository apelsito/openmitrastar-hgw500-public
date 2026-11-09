"""Derive bounded DFS467 residual audit from immutable prior module auditor."""
from pathlib import Path

def main():
 src=Path(__file__).with_name('audit_hgw5g_coex26_modules.py');out=src.with_name('audit_hgw5g_dfs467_modules.py');assert not out.exists();s=src.read_text();a=s.index('CHANGED=');b=s.index('\ndef digest',a)
 config="""CHANGED={'wlan':{'ieee80211_ioctl_getparam'},'wlan_scan_ap':{'ap_pick_channel'}}
NEW={'wlan':{'om_ieee80211_dfs_channel_available'},'wlan_scan_ap':set()}
EXPORTS={'om_ieee80211_dfs_channel_available'}
RENAME={}
DIAG={'ieee80211_delete_wlanunit':[(44,'8553','8c53'),(116,'8653','8d53')],'ieee80211_ioctl_giwfreq':[(76,'980d','d80d')],'ieee80211_param_from_qdrv':[(92,'950d','960d')],'ieee80211_ioctl_setparam':[(12702,'ee33','ef33')],'ap_end':[(104,'ce09','0e0b')]}
COMPACT=set()
""";s=s[:a]+config+s[b:];s=s.replace("assert set(diagnostics)==({k for k in DIAG if k!='qdrv_wlan_exit'}if component=='wlan'else{'qdrv_wlan_exit'})","assert set(diagnostics)==({k for k in DIAG if k!='ap_end'}if component=='wlan'else{'ap_end'})")
 s=s.replace("table_old['size']==591*24 and table_new['size']==592*24","table_old['size']==595*24 and table_new['size']==596*24")
 s=s.replace("x,p)[0]==591 and struct.unpack_from('<H',y,p)[0]==592","x,p)[0]==595 and struct.unpack_from('<H',y,p)[0]==596").replace("struct.pack_into('<H',z,p,591)","struct.pack_into('<H',z,p,595)")
 s=s.replace("expected=(6 if component=='wlan'else 0)if sec=='.text'else 0","expected=0 # exact value calibrated from parsed whole selected modules below")
 s=s.replace("if component=='qdrv':pass","if component=='wlan_scan_ap':pass")
 s=s.replace("choices=['qdrv','wlan']","choices=['wlan_scan_ap','wlan']").replace('PASS_COMPLETE_COEX26_RESIDUAL_MODULE_SCOPE','PASS_COMPLETE_DFS467_BOUNDED_RESIDUAL_MODULE_SCOPE');out.write_text(s,newline='\n');print(out)

if __name__=='__main__':main()
