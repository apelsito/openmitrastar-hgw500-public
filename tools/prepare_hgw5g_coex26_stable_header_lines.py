"""Retain Source26's policy/prototype without shifting old header line numbers.

Only a new source version is created. Header inserts share old declaration
lines so inlined OEM __LINE__ diagnostic constants remain at old positions.
Full old-field ABI still requires a separate compiler witness.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();proof=json.loads((a.parent/'result.json').read_text());assert proof['total_original_entries_added']==26;a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');h=a.output/'headers/net80211/ieee80211_var.h';text=h.read_text();old=a.baseline/'headers/net80211/ieee80211_var.h';before=old.read_text();needle='\tbool om_coc_pm_pending;\n\t/* OEM449 policy in unused host padding; ARC witness is mandatory. */\n\tu8 om_20_40_bss_coex;\n';assert text.count(needle)==1;text=text.replace(needle,'\tbool om_coc_pm_pending; u8 om_20_40_bss_coex; /* OEM449: prior padding. */\n',1);proto='void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap);\nvoid om_ieee80211_change_bw(struct ieee80211vap *vap,int bw,int delay_ch_switch);';assert text.count(proto)==1;text=text.replace(proto,proto.replace('\n',' '),1)
 assert len(text.splitlines())==len(before.splitlines());normalized=text.replace('\tbool om_coc_pm_pending; u8 om_20_40_bss_coex; /* OEM449: prior padding. */','\tbool om_coc_pm_pending;').replace('void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap); void om_ieee80211_change_bw(struct ieee80211vap *vap,int bw,int delay_ch_switch);','void ieee80211_start_obss_scan_timer(struct ieee80211vap *vap);');assert normalized==before,'unrelated header text drift';h.write_text(text,newline='\n');result=dict(proof);result.update(status='SOURCE_ONLY_COEX26_PADDING_SAME_HEADER_LINE_POSITIONS_PENDING_GATES',parent_source=str(a.parent),changed_sources={**proof['changed_sources'],'headers/net80211/ieee80211_var.h':sha(h)},old_header_lines_preserved=True,old_header_line_count=len(before.splitlines()),header_delta='Onlyu8policy/prototype on existinglines; everyotherbyteofheader unchanged',limits='Sourceonly; ABI recheck, actualpairedchangedunits andglobaldelta stillrequired; noRF/PHY/trafficacceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
