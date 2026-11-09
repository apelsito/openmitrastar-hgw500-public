"""Freeze strict467 auditor at32table context; inspect explicitdiagnostics only."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
src=(ROOT/'tools/audit_hgw5g_dfs467_modules.py').read_text();src=src.replace('595','598').replace('596','599')
src=src.replace("DIAG={'ieee80211_delete_wlanunit':[(44,'8553','8c53'),(116,'8653','8d53')],'ieee80211_ioctl_giwfreq':[(76,'980d','d80d')],'ieee80211_param_from_qdrv':[(92,'950d','960d')],'ieee80211_ioctl_setparam':[(12702,'ee33','ef33')],'ap_end':[(104,'ce09','0e0b')]}","DIAG={}")
target=ROOT/'tools/audit_consolidated32_bounded467_modules.py';assert not target.exists();target.write_text(src,newline='\n')
