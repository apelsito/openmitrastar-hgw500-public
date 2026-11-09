"""RecoveractualOEM490 statefulrate/mode dispatch as new23-recordSOURCE.

Two per-radio fieldsappendatend ofieee80211com; sourcepreserveseveryoldfield.
Callback/wire ordering matchesOEM: updateownedstate,wire62,profile/mode changes,
setmode,CSAconfigreason,reassoc,HOSTAPchannelcallback. No hardwareexecution.
Allheader-users/fullmoduleABI/deltagate mandatory; no23releaseorperformanceclaim.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

HELPER='''/* RecoveredOEM490: radio-scopedsavedmode/state, notperVAPfixedratecache.
 * Legacynegativevalues allrestore. Hostcallbacks arevoid, so noasynchronous
 * MuC/PHYsuccessis asserted by this controlflow return. */
static int om_fix_legacy_rate(struct ieee80211vap *vap,int value)
{
    struct ieee80211com *ic=vap->iv_ic;
    int target=-1;
    u32 wire;
    if(value<0){
        if(!ic->om_legacy_rate_fixed)return -EINVAL;
        target=ic->om_legacy_rate_saved_mode;
        ic->om_legacy_rate_fixed=0;
        ic->om_legacy_rate_saved_mode=0;
        if((unsigned)(target-1)<6U)target=-1;
        wire=255U;
    }else{
        if(value>12)return -EINVAL;
        wire=0x7f000000U|(u32)value|((u32)value<<8)|((u32)value<<16);
        if((u16)(ic->ic_curmode-1U)<6U)target=-1;
        else if(ic->ic_phymode==1||ic->ic_phymode==7||ic->ic_phymode==10||
                (unsigned)(ic->ic_phymode-11)<4U)target=1;
        else target=3;
        if(!ic->om_legacy_rate_fixed){
            ic->om_legacy_rate_saved_mode=ic->ic_curmode;
            ic->om_legacy_rate_fixed=1;
        }
    }
    ieee80211_param_to_qdrv(vap,IEEE80211_PARAM_FIXED_TX_RATE,(int)wire,NULL,0);
    if(target!=-1){
        if(ic->ic_rf_chipid==CHIPID_DUAL&&ic->ic_opmode==IEEE80211_M_STA){
            if(ic->ic_phymode==1||ic->ic_phymode==7||ic->ic_phymode==10||
               (unsigned)(ic->ic_phymode-11)<4U)
                vap->iv_5ghz_prof.vht=target>10;
            else vap->iv_2_4ghz_prof.vht=target>10;
        }
        ic->ic_des_mode=target;
        ic->ic_phymode=target;
        ieee80211_setmode(ic,target);
        ic->ic_csw_reason=IEEE80211_CSW_REASON_CONFIG;
        ieee80211_wireless_reassoc(vap,0,1);
        if(vap->iv_opmode==IEEE80211_M_HOSTAP)
            ic->ic_set_channel(ic);
    }
    return 0;
}

'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();parent=json.loads((a.parent/'result.json').read_text());assert parent['total_original_entries_added']==22
 a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');header=a.output/'headers/net80211/ieee80211_var.h';oldh=header.read_text();anchor='\tstruct sta_dfs_info sta_dfs_info;\n};';assert oldh.count(anchor)==1
 fields='\t/* RecoveredOEM490per-radio state; existingmemberprefix remains intact. */\n\tint om_legacy_rate_saved_mode;\n\tint om_legacy_rate_fixed;\n';header.write_text(oldh.replace(anchor,'\tstruct sta_dfs_info sta_dfs_info;\n'+fields+'};',1),newline='\n')
 path=a.output/'source/wlan/ieee80211_wireless.c';old=path.read_text();new=old.replace('#define OM_OEM_PARAM_DEVICE_MODE 451','#define OM_OEM_PARAM_FIX_LEGACY_RATE 490\n#define OM_OEM_PARAM_DEVICE_MODE 451',1)
 start=new.index('static int\nieee80211_ioctl_setparam(');new=new[:start]+HELPER+new[start:]
 start=new.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=new.index('{',new.index('switch (param)',start));case='\n\tcase OM_OEM_PARAM_FIX_LEGACY_RATE:\n\t\treturn om_fix_legacy_rate(vap,value);\n';new=new[:brace+1]+case+new[brace+1:]
 start=new.index('static const struct iw_priv_args ieee80211_priv_args[]');end=new.index('\n};',start);entry='\n\t{ OM_OEM_PARAM_FIX_LEGACY_RATE,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,0,"fix_legacy_rate" },';new=new[:end]+entry+new[end:];path.write_text(new,newline='\n')
 patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/src/wlan/ieee80211_wireless.c',tofile='b/src/wlan/ieee80211_wireless.c'))+''.join(difflib.unified_diff(oldh.splitlines(True),header.read_text().splitlines(True),fromfile='a/vendor/port-context/drivers/include/kernel/net80211/ieee80211_var.h',tofile='b/vendor/port-context/drivers/include/kernel/net80211/ieee80211_var.h'));(a.output/'legacy490-recovery.patch').write_text(patch,newline='\n')
 result=dict(status='SOURCE_ONLY_STATEFUL490_23_RECORDS_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,total_original_entries_added=23,remaining_original_table_gaps=21,wireless_sha256=sha(path),header_sha256=sha(header),parent_manifest_sha256=sha(a.parent/'result.json'),new_state='2ints per-radio IEEE80211com tail, existingQDRVmemset sizeof initializes0',wire='FIXED_TX_RATE62 encoded0x7f repeated0..12 or255restore',errorpaths='Inactiveanynegative/positive>12 EINVAL nochanges; voidcallbacks cannotconfirmhardwarecompletion',gates=['AllQDRV/WLAN/ancillaryheader-usersrecompile','ARC209VAPprefix andICprefix/newQDRVembeddingoffsetaudit','Actualstatefulfunctionfixtures withwire/callbackorder','NoPHY/rate/trafficphysicalacceptance'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
