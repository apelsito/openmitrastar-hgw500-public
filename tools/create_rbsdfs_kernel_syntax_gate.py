"""Derive fouractualunitsARC gate withonlyonecompiler andimmutabledeps."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=(ROOT/'tools/compile_consolidated32_units.py').read_text().replace("[('wlan','ieee80211_scan'),('wlan_scan_ap','ieee80211_scan_ap'),('wlan','ieee80211_proto'),('wlan','ieee80211_wireless')]","[('qdrv','qdrv_wlan'),('qdrv','qdrv_radar'),('wlan','ieee80211'),('wlan','ieee80211_wireless')]")
s=s.replace('PASS_ACTUAL_CONSOLIDATED32_FOUR_TYPED_UNITS_INC_PIN_CLOSURE','PASS_ARC_RBSDFS_KERNEL_FOUR_TYPED_UNITS_ONLY_PROVIDER_UNBOUND')
t=ROOT/'tools/compile_hgw5g_rbsdfs_kernel_units.py';assert not t.exists();t.write_text(s,newline='\n')
