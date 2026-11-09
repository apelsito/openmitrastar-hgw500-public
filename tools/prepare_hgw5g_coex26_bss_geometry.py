"""Reconcile real OEM449 geometry against BSS channel, preserve old source.

Exact OEM check40/public coex geometry uses BSS +0x4e08; the retained source
used current channel. Keep its original comments, use one BSS snapshot and
refuse NULL/ANYC instead of the OEM unchecked dereference. Match low16 math
and signed8 scan channel inputs observed in OEM instruction evidence.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();proof=json.loads((a.parent/'result.json').read_text());assert proof['total_original_entries_added']==26;a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');path=a.output/'source/wlan/ieee80211_input.c';old=path.read_text();start=old.index('int\nieee80211_20_40_operation_permitted(');end=old.index('int\nieee80211_check_mode(',start);fragment=old[start:end]
 fragment=fragment.replace('struct ieee80211com *ic = vap->iv_ic;','struct ieee80211com *ic = vap->iv_ic;\n\tstruct ieee80211_channel *bss = READ_ONCE(ic->ic_bsschan);',2).replace('ic->ic_curchan->','bss->')
 needle='\tpri_chan = bss->ic_ieee;';assert fragment.count(needle)==1;fragment=fragment.replace(needle,'\t/* OEM449 uses BSS geometry even while a scan has another current channel. */\n\tif (!bss || bss == IEEE80211_CHAN_ANYC)\n\t\treturn 0;\n'+needle,1)
 needle='\tch_freq = ieee80211_ieee2mhz(channel, 0);';assert fragment.count(needle)==1;fragment=fragment.replace(needle,'\tif (!bss || bss == IEEE80211_CHAN_ANYC)\n\t\treturn 0;\n'+needle,1)
 fragment=fragment.replace('ieee80211_ieee2mhz(se_pri_chan, 0)','ieee80211_ieee2mhz((int8_t)se_pri_chan, 0)',1).replace('ieee80211_ieee2mhz(se_sec_chan, 0)','ieee80211_ieee2mhz((int8_t)se_sec_chan, 0)',1)
 # Instructionextb forinputchannel andsecondarycurrent, compare signedinput
 # to originalzeroextended BSSprimary: invalidhigh8numbers never sameBSS.
 fragment=fragment.replace('(pri_chan == se_pri_chan)','((int)pri_chan == (int8_t)se_pri_chan)').replace('(sec_chan == se_sec_chan)','((int8_t)sec_chan == (int8_t)se_sec_chan)')
 new=old[:start]+fragment+old[end:];path.write_text(new,newline='\n');(a.output/'coex449-bss-geometry.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/source/wlan/ieee80211_input.c',tofile='b/source/wlan/ieee80211_input.c')),newline='\n');result=dict(proof);result.update(status='SOURCE_ONLY_COEX26_OEM_BSS_GEOMETRY_PENDING_ACTUAL_FIXTURE_AND_MODULES',parent_source=str(a.parent),changed_sources={**proof['changed_sources'],'source/wlan/ieee80211_input.c':sha(path)},geometry='OEMBSSchan+0x4e08 snapshot, low16frequency bounds, signed8scanchannelconversion; publicreportchannelunsignedbyte',geometry_safety='NULL/ANYCBSS returnsnotpermitted withoutcallbacks insteadOEMuncheckedpointer',limits='Prior26r2modulesnotselected; actualgeometrymath/publicconsumerfixtures/newpairedinputunit/globaldelta/reviewrequired; noRF/PHY/regulatoryacceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
