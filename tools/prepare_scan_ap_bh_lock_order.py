"""Prepare isolated AP scan-list BH ordering correction, no hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import difflib
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();old=a.source.read_text();new=old
 lock='\tspin_lock(&as->asl_lock);\n\tif (bh_disabled) {\n\t\tlocal_bh_disable();\n\t}'
 unlocked='\tif (bh_disabled) {\n\t\tlocal_bh_enable();\n\t}\n\tspin_unlock(&as->asl_lock);'
 assert new.count(lock)==1 and new.count(unlocked)==1
 new=new.replace(lock,'\tif (bh_disabled) {\n\t\tlocal_bh_disable();\n\t}\n\tspin_lock(&as->asl_lock);',1)
 new=new.replace(unlocked,'\tspin_unlock(&as->asl_lock);\n\tif (bh_disabled) {\n\t\tlocal_bh_enable();\n\t}',1)
 a.output.mkdir(parents=True);(a.output/'source/wlan').mkdir(parents=True);(a.output/'headers').mkdir();dst=a.output/'source/wlan/ieee80211_scan_ap.c';dst.write_text(new,newline='\n');(a.output/'scan-ap-bh-lock.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/ieee80211_scan_ap.c',tofile='b/ieee80211_scan_ap.c')),newline='\n');v={'status':'SOURCE_ONLY_SCAN_AP_BH_ORDER_FIX_PENDING_FIXTURE_ARC','hardware_accessed':False,'firmware_eligible':False,'source_before':sha(a.source),'source_after':sha(dst),'header_or_wire_changes':False,'change':'Disablebottomhalvesbeforetakingspinlock; unlockbeforeenablingbottomhalves; priorcontext conditionalunchanged','scope':'UPprocess/softirqscanlist serialization; hardIRQwarning preserved'};(a.output/'result.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v,indent=2))
if __name__=='__main__':main()
