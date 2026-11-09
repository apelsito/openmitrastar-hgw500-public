"""Source-only OEM493 BSSTM state/callsite reconstruction.

Preserves old net80211 struct prefix with a host-only append; patch actual
beacon/probe/association response appIE copies. Does not add BSSTM action
handlers or claim802.11v/client support. ShortTLVs and wrong copiedlength are
explicit guarded differences from OEM. Fullheader-dependent rebuild required.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil


ROOT=Path(__file__).resolve().parents[1]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

HELPER='''/* Derived OEM493 ExtCapIE127 payloadbyte2 bit3 update. Guard shortTLVs
 * and use the length actually copied; no management action handler is added. */
static inline int om_bss_tm_update_ie(u8 *ies,size_t length,u32 enabled)
{
    size_t pos=0;
    while(pos<length){
        size_t n;
        if(length-pos<2)return -EINVAL;
        n=ies[pos+1];
        if(n>length-pos-2)return -EINVAL;
        if(ies[pos]==127){
            if(n<3)return -EINVAL;
            if(enabled & 1U)ies[pos+4]|=8U;
            else ies[pos+4]&=(u8)~8U;
            return 1;
        }
        pos+=n+2;
    }
    return 0;
}

'''


def main():
 p=argparse.ArgumentParser();p.add_argument('--wlan-parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 assert sha(a.wlan_parent)=='538da528ed69173af54bb5f7c8001e75254fadc883b6464e6674cff2d83e9cb2'
 a.output.mkdir(parents=True,exist_ok=False);src=a.output/'source/wlan';src.mkdir(parents=True)
 base=ROOT/'work/linux510-radio-port/quantenna/wlan'
 for path in base.iterdir():
  if path.is_file()and path.suffix in('.c','.h')and not path.name.endswith('.mod.c'):shutil.copyfile(path,src/path.name)
 source=src/'ieee80211_wireless.c';shutil.copyfile(a.wlan_parent,source)
 headerbase=ROOT/'work/sources/Quantenna-GPL/drivers/include/kernel/net80211/ieee80211_var.h';header=a.output/'headers/net80211/ieee80211_var.h';header.parent.mkdir(parents=True)
 old_header=headerbase.read_text();field='\t/* Recovered OEM493 host-only state; all existing fields remain before it. */\n\tu32 om_bss_tm_flags;\n'
 anchor='\tstruct sta_dfs_info sta_dfs_info;\n};';assert old_header.count(anchor)==1
 header.write_text(old_header.replace(anchor,'\tstruct sta_dfs_info sta_dfs_info;\n'+field+'};'),newline='\n')
 h=src/'openmitrastar_bss_tm.h';h.write_text('#ifndef OPENMITRASTAR_BSS_TM_H\n#define OPENMITRASTAR_BSS_TM_H\n#include <linux/types.h>\n#include <linux/stddef.h>\n#include <linux/errno.h>\n'+HELPER+'#endif\n')
 originals={};patches=[]
 for path in(source,src/'ieee80211_beacon_desc.c',src/'ieee80211_output.c'):
  originals[path.name]=path.read_text()
  text=originals[path.name]
  marker='#include <linux/version.h>'
  if marker not in text:
   marker='#include <linux/skbuff.h>'
  assert marker in text,path.name
  text=text.replace(marker,marker+'\n#include "openmitrastar_bss_tm.h"',1)
  if path.name=='ieee80211_wireless.c':
   text=text.replace('#define OM_OEM_PARAM_DEVICE_MODE 451','#define OM_OEM_PARAM_BSS_TM 493\n#define OM_OEM_PARAM_DEVICE_MODE 451',1)
   start=text.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=text.index('{',text.index('switch (param)',start))
   block='\n\tcase OM_OEM_PARAM_BSS_TM:\n\t\tif(value == 1)ic->om_bss_tm_flags |= 1U;\n\t\telse ic->om_bss_tm_flags &= ~1U;\n\t\tieee80211_beacon_update_all(ic);\n\t\tbreak;\n';text=text[:brace+1]+block+text[brace+1:]
   start=text.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=text.index('{',text.index('switch (param[0] & 0xffff)',start))
   block='\n\tcase OM_OEM_PARAM_BSS_TM:\n\t\tparam[0] = ic->om_bss_tm_flags & 1U;\n\t\tbreak;\n';text=text[:brace+1]+block+text[brace+1:]
   start=text.index('static const struct iw_priv_args ieee80211_priv_args[]');end=text.index('\n};',start)
   entries='\n\t{ OM_OEM_PARAM_BSS_TM,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, 0, "bss_tm" },\n\t{ OM_OEM_PARAM_BSS_TM,\n\t  0, IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1, "get_bss_tm" },';text=text[:end]+entries+text[end:]
  elif path.name=='ieee80211_beacon_desc.c':
   marker='\t\tfrm += vap->app_ie[IEEE80211_APPIE_FRAME_BEACON].length;'
   assert text.count(marker)==1
   text=text.replace(marker,'\t\t(void)om_bss_tm_update_ie(frm,\n\t\t    vap->app_ie[IEEE80211_APPIE_FRAME_BEACON].length,\n\t\t    ic->om_bss_tm_flags);\n'+marker,1)
  else:
   for frame in('PROBE_RESP','ASSOC_RESP'):
    marker='\t\t\tfrm += vap->app_ie[IEEE80211_APPIE_FRAME_'+frame+'].length;';assert text.count(marker)==1
    text=text.replace(marker,'\t\t\t(void)om_bss_tm_update_ie(frm,\n\t\t\t    vap->app_ie[IEEE80211_APPIE_FRAME_'+frame+'].length,\n\t\t\t    ic->om_bss_tm_flags);\n'+marker,1)
  path.write_text(text,newline='\n');patches.append(''.join(difflib.unified_diff(originals[path.name].splitlines(True),text.splitlines(True),fromfile='a/src/wlan/'+path.name,tofile='b/src/wlan/'+path.name)))
 patches.append(''.join(difflib.unified_diff(old_header.splitlines(True),header.read_text().splitlines(True),fromfile='a/vendor/port-context/drivers/include/kernel/net80211/ieee80211_var.h',tofile='b/vendor/port-context/drivers/include/kernel/net80211/ieee80211_var.h')))
 (a.output/'bss-tm-consumer-integration.patch').write_text(''.join(patches),newline='\n')
 result=dict(status='SOURCE_ONLY_BSS_TM_COPIED_IE_INTEGRATION_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,parent_wlan_sha256=sha(a.wlan_parent),changed_sources={n:sha(src/n)for n in originals},header_sha256=sha(header),helper_sha256=sha(h),total_original_table_entries_added=17,actual_functional_entries_recovered=15,faithful_unsupported_entries=2,remaining_original_table_gaps=27,callers=['beacon_appIE_descriptor','probe_response_appIE','association_response_appIE'],explicit_behavior_delta='ShortTLVbounds; associationresponse usesitsactualcopiedlength (OEMusedproberesponselength)',gates=['CompleteallWLANandQDRVheader-userrebuild withoverlayheadersfirst','ARCexistingprefixABIoffsets unchanged,sizeextensionpermitted','Fullmodules/tests; no80211vactionhandler/clientacceptanceclaim'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
