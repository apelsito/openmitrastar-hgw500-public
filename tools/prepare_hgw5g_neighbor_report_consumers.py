"""SOURCE-only492 neighbor capability toggle with actual frame/descriptor users.

Extends493SOURCE candidate; does not add neighbor-report management action
handlers or assert802.11k functionality. Recovered flag drives RRMcapability
bits/IEs and immediatebeacon descriptor bytes with explicit7byte capacity.
Fullheader-user rebuild, ABI, module/delta and allruntime gates remain pending.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 proof=json.loads((a.parent/'result.json').read_text());assert proof['total_original_table_entries_added']==17
 a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
 src=a.output/'source/wlan';header=a.output/'headers/net80211/ieee80211_var.h';old=header.read_text();anchor='\tu32 om_bss_tm_flags;\n';assert old.count(anchor)==1;header.write_text(old.replace(anchor,anchor+'\t/* Recovered OEM492 host-only NeighborReport capability state. */\n\tu32 om_neighbor_report_flags;\n'),newline='\n')
 helper=src/'openmitrastar_bss_tm.h';h=helper.read_text();addition='''/* Exact OEM RRMcapabilityIE: id70,len5, bit1 whenNeighborReport selected. */
static inline u8 *om_neighbor_rrm_ie(u8 *frm,u32 selected)
{
    size_t n;
    for(n=0;n<7;n++)frm[n]=0;
    frm[0]=70;frm[1]=5;frm[2]=(selected&1U)?2U:0U;
    return frm+7;
}

''';helper.write_text(h.replace('#endif\n',addition+'#endif\n'),newline='\n')
 originals={};diffs=[]
 for name in('ieee80211_wireless.c','ieee80211_beacon.c','ieee80211_beacon_desc.c','ieee80211_output.c'):
  path=src/name;originals[name]=path.read_text();text=originals[name]
  if name=='ieee80211_wireless.c':
   text=text.replace('#define OM_OEM_PARAM_BSS_TM 493','#define OM_OEM_PARAM_NEIGHBOR_REPORT 492\n#define OM_OEM_PARAM_BSS_TM 493',1)
   start=text.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=text.index('{',text.index('switch (param)',start));setcase='\n\tcase OM_OEM_PARAM_NEIGHBOR_REPORT:\n\t\tif(value == 1)ic->om_neighbor_report_flags |= 1U;\n\t\telse ic->om_neighbor_report_flags &= ~1U;\n\t\tieee80211_beacon_update_all(ic);\n\t\tbreak;\n';text=text[:brace+1]+setcase+text[brace+1:]
   start=text.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=text.index('{',text.index('switch (param[0] & 0xffff)',start));getcase='\n\tcase OM_OEM_PARAM_NEIGHBOR_REPORT:\n\t\tparam[0] = ic->om_neighbor_report_flags & 1U;\n\t\tbreak;\n';text=text[:brace+1]+getcase+text[brace+1:]
   start=text.index('static const struct iw_priv_args ieee80211_priv_args[]');end=text.index('\n};',start);entries='\n\t{ OM_OEM_PARAM_NEIGHBOR_REPORT,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "neigh_repo" },\n\t{ OM_OEM_PARAM_NEIGHBOR_REPORT,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_neigh_repo" },';text=text[:end]+entries+text[end:]
  elif name=='ieee80211_beacon.c':
   marker='#include <linux/version.h>';assert marker in text;text=text.replace(marker,marker+'\n#include "openmitrastar_bss_tm.h"',1)
   marker='\t\tcapinfo |= IEEE80211_CAPINFO_SPECTRUM_MGMT;';assert text.count(marker)==2;text=text.replace(marker,marker+'\n\tif(ic->om_neighbor_report_flags & 1U)\n\t\tcapinfo |= 0x1000U;')
   # Alwaysreserve/retain7B descriptorIE for reversibleliveflagbit updates;
   # this addsdisabledRRMIE as explicitSOURCEdelta from OEMoptionalinclusion.
   marker='\t/* BSS load element */';assert text.count(marker)==1;text=text.replace(marker,'\tfrm = ieee80211_add_beacon_desc_ie(ni, 70, frm);\n\n'+marker,1)
   marker='\t\t + sizeof(struct ieee80211_ie_qtn)';assert marker in text;text=text.replace(marker,marker+'\n\t\t + 7 /* RecoveredRRMIE70 descriptor reserve */',1)
   marker='\t*bo->bo_caps = htole16(capinfo);';assert text.count(marker)==1;text=text.replace(marker,marker+'\n\tif(bo->bo_om_rrm)\n\t\t(void)om_neighbor_rrm_ie(bo->bo_om_rrm,ic->om_neighbor_report_flags);',1)
   # Track thedescriptorIE pointer intheexistingbeaconoffsetstruct append.
   marker='\tfrm = ieee80211_add_beacon_desc_ie(ni, 70, frm);';text=text.replace(marker,'\tbo->bo_om_rrm = frm;\n'+marker,1)
  elif name=='ieee80211_beacon_desc.c':
   marker='\tcase IEEE80211_ELEMID_RATES:';assert marker in text;text=text.replace(marker,'\tcase 70:\n\t\tfrm = om_neighbor_rrm_ie(frm,ic->om_neighbor_report_flags);\n\t\tbreak;\n'+marker,1)
  else:
   # Only AP probe/assocresponse cases; no clientactiondispatch is introduced.
   for frame in('PROBE_RESP','ASSOC_RESP'):
    marker='vap->app_ie[IEEE80211_APPIE_FRAME_'+frame+'].length';# allocationhasdifferentindent aroundexpression
    before=text.index(marker);text=text[:before]+text[before:].replace(marker,marker+' + 7 /* recoveredRRMIE reserve */',1)
   probe=text.index('case IEEE80211_FC0_SUBTYPE_PROBE_RESP:');assoc=text.index('case IEEE80211_FC0_SUBTYPE_ASSOC_RESP:')
   # Insert beforeappIEcopy wherecapacityalreadyreserved; conditionalmatchesOEM.
   for frame in('PROBE_RESP','ASSOC_RESP'):
    marker='\t\tif (vap->app_ie[IEEE80211_APPIE_FRAME_'+frame+'].ie) {';assert text.count(marker)==1
    text=text.replace(marker,'\t\tif(ic->om_neighbor_report_flags & 1U)\n\t\t\tfrm = om_neighbor_rrm_ie(frm,ic->om_neighbor_report_flags);\n\n'+marker,1)
   # Capabilitywordforresponse: findonlyinprobe/assocresponse case region.
   positions=[]
   for label in('case IEEE80211_FC0_SUBTYPE_PROBE_RESP:','case IEEE80211_FC0_SUBTYPE_ASSOC_RESP:'):
    start=text.index(label);end=text.index('*(__le16 *)frm = htole16(capinfo);',start);positions.append(end)
   for end in sorted(positions,reverse=True):text=text[:end]+'if(ic->om_neighbor_report_flags & 1U)\n\t\t\tcapinfo |= 0x1000U;\n\t\t'+text[end:]
  path.write_text(text,newline='\n');diffs.append(''.join(difflib.unified_diff(originals[name].splitlines(True),text.splitlines(True),fromfile='a/src/wlan/'+name,tofile='b/src/wlan/'+name)))
 # Append bookkeepingpointer tohostbeaconoffsets, notMuCdescriptorwirelayout.
 root=Path(__file__).resolve().parents[1];bbase=root/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_beacon.h'
 if not bbase.exists():
  candidates=[]
  for path in(root/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211').glob('*.h'):
   if 'struct ieee80211_beacon_offsets {' in path.read_text():candidates.append(path)
  assert len(candidates)==1; bbase=candidates[0]
 btext=bbase.read_text();start=btext.index('struct ieee80211_beacon_offsets {');end=btext.index('\n};',start);new=btext[:end]+'\n\tu8 *bo_om_rrm; /* host-onlyrecoveredRRMIE pointer */'+btext[end:]
 dest=a.output/'headers/net80211'/bbase.name;dest.write_text(new,newline='\n')
 (a.output/'neighbor-capability-integration.patch').write_text(''.join(diffs),newline='\n')
 result=dict(status='SOURCE_ONLY_NEIGHBOR_CAPABILITY_CONSUMERS_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,total_original_entries_added=19,functional_entries_source=17,unsupported_faithful=2,remaining_original_table_gaps=25,changed_sources={n:sha(src/n)for n in originals},host_headers={x.name:sha(x)for x in(a.output/'headers/net80211').iterdir()},helper_sha256=sha(helper),explicit_behavior_delta='Beaconkeeps7byteRRMIEwithzeroNeighborbitwhen disabledforreversibleupdates; OEMconditionalpresence',limits=['No80211kactionhandlerorclientproof.','FullQDRV/WLAN/scan/cryptoheader-userrebuild required.','Flagwritersserialization anddescriptorupdatesconsistencyunproven untiltests.'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
