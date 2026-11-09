"""Create dedicated Coex26 residual auditor without altering frozen CoC25."""
from pathlib import Path

def main():
 original=Path(__file__).with_name('audit_hgw5g_coc25_controlled_modules.py');target=original.with_name('audit_hgw5g_coex26_modules.py');assert not target.exists();s=original.read_text();a=s.index('CHANGED=');b=s.index('\ndef digest(',a)
 config="""CHANGED={'qdrv':{'qdrv_wlan_init'},'wlan':{'ieee80211_ioctl_setparam','ieee80211_recv_action_public_coex.isra.0','ieee80211_check_mode','ieee80211_start_obss_scan_timer','ieee80211_recv_mgmt'}}
NEW={'qdrv':set(),'wlan':{'om_ieee80211_change_bw'}}
EXPORTS={'om_ieee80211_change_bw'}
RENAME={}
DIAG={'qdrv_wlan_exit':[(962,'f723','f823')],'ieee80211_delete_wlanunit':[(44,'5353','5b53'),(116,'5453','5c53')],'ieee80211_ioctl_giwfreq':[(76,'d80c','180d')],'ieee80211_param_from_qdrv':[(92,'920d','930d')],'ieee80211_repeater_csa_finish':[(62,'d50d','1609')],'ieee80211_sta_assocs_dec':[(76,'4b0b','780b'),(114,'4c0b','790b'),(174,'4d0b','7a0b')],'ieee80211_node_leave':[(686,'950e','c20e')],'ieee80211_node_join':[(442,'490d','760d')]}
COMPACT=set()
"""
 s=s[:a]+config+s[b:];s=s.replace("assert component=='wlan',('unrelated QDRV function',k);repair(k[0],x,y)","assert k[0]in DIAG,('unrelated function',k);repair(k[0],x,y)")
 s=s.replace("if component=='wlan':assert set(diagnostics)==set(DIAG)|COMPACT","assert set(diagnostics)==({k for k in DIAG if k!='qdrv_wlan_exit'}if component=='wlan'else{'qdrv_wlan_exit'})")
 # No diagnostic width change in this candidate. Delete only admitted bodies;
 # verify anonymous bodies anchored to their following existing functions.
 start=s.index("    if component=='wlan':\n     if name in(");end=s.index('    if oldn:oldranges.append',start);s=s[:start]+s[end:]
 s=s.replace("expected=(2 if component=='wlan'else -2)if sec=='.text'else 0","expected=(6 if component=='wlan'else 0)if sec=='.text'else 0")
 s=s.replace("table_old['size']==589*24 and table_new['size']==591*24","table_old['size']==591*24 and table_new['size']==592*24")
 s=s.replace('value-=48','value-=24').replace('y[cut+48:]','y[cut+24:]').replace("x,p)[0]==589 and struct.unpack_from('<H',y,p)[0]==591","x,p)[0]==591 and struct.unpack_from('<H',y,p)[0]==592").replace("struct.pack_into('<H',z,p,589)","struct.pack_into('<H',z,p,591)")
 old="strings=lambda z:Counter(v for v in z.split(b'\\0')if v);assert not(strings(x)-strings(y))and strings(y)-strings(x)==Counter({b'CoC: Channel changed to %d as PM level changed to %d\\n':1})";new="strings=lambda z:Counter(v for v in z.split(b'\\0')if v);assert strings(x)==strings(y),'all existing strings'";assert old in s;s=s.replace(old,new)
 s=s.replace("if component=='qdrv':expected_new.add('om_ieee80211_coc_quiesce')","if component=='qdrv':pass")
 s=s.replace('PASS_COMPLETE_COC25_RESIDUAL_SAME_HEADER_SCOPE','PASS_COMPLETE_COEX26_RESIDUAL_MODULE_SCOPE');target.write_text(s,newline='\n');print(target)

if __name__=='__main__':main()
