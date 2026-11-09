"""Recover OEM478 boolean and actual AP weather-channel selection consumer.

Use prior IC padding to preserve all old host layout. CAC duration/marking,
radar restrictions and regulatory policy remain in their existing consumers.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
from collections import Counter
from catalog_hgw_firmware_comments import scan_comments


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
    proof=json.loads((a.parent/'result.json').read_text());assert proof['source_original_records']==32
    shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
    changes={};patch=[]
    def change(relative,new):
        path=a.output/relative;old=path.read_bytes();raw=new.encode('utf-8')
        comments=lambda b:Counter(b[r['offset']:r['end_offset']]for r in scan_comments(b))
        assert not comments(old)-comments(raw),'old comment lost '+relative
        path.write_bytes(raw);changes[relative]=sha(path)
        patch.extend(difflib.unified_diff(old.decode().splitlines(True),new.splitlines(True),fromfile='a/'+relative,tofile='b/'+relative))
    relative='headers/net80211/ieee80211_var.h';text=(a.output/relative).read_text()
    needle='\tuint8_t ic_rx_bar_sync;\n';assert text.count(needle)==1
    change(relative,text.replace(needle,'\tuint8_t ic_rx_bar_sync; u8 om_weather_cac_enabled; /* OEM478: former padding. */\n',1))
    relative='source/qdrv/qdrv_wlan.c';text=(a.output/relative).read_text()
    needle='\tic->om_20_40_bss_coex = 1;';assert text.count(needle)==1
    change(relative,text.replace(needle,'\tic->om_weather_cac_enabled = 0;\n'+needle,1))
    relative='source/wlan/ieee80211_scan_ap.c';text=(a.output/relative).read_text()
    needle='\t\tif (ieee80211_is_on_weather_channel(ic, ic_best_chan)) {';assert text.count(needle)==1
    change(relative,text.replace(needle,'\t\tif (!READ_ONCE(ic->om_weather_cac_enabled) &&\n\t\t    ieee80211_is_on_weather_channel(ic, ic_best_chan)) {',1))
    relative='source/wlan/ieee80211_wireless.c';text=(a.output/relative).read_text()
    text=text.replace('#define OM_OEM_PARAM_BW_AUTOSEL 461','#define OM_OEM_PARAM_WEATHER_CAC_ENABLE 478\n#define OM_OEM_PARAM_BW_AUTOSEL 461',1)
    start=text.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');switch=text.index('switch (param)',start);brace=text.index('{',switch)
    text=text[:brace+1]+'\n\tcase OM_OEM_PARAM_WEATHER_CAC_ENABLE:\n\t\tWRITE_ONCE(ic->om_weather_cac_enabled,!!value);\n\t\treturn 0;\n'+text[brace+1:]
    start=text.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');switch=text.index('switch (param[0] & 0xffff)',start);brace=text.index('{',switch)
    text=text[:brace+1]+'\n\tcase OM_OEM_PARAM_WEATHER_CAC_ENABLE:\n\t\tparam[0]=READ_ONCE(ic->om_weather_cac_enabled);\n\t\treturn 0;\n'+text[brace+1:]
    start=text.index('static const struct iw_priv_args ieee80211_priv_args[]');end=text.index('\n};',start)
    text=text[:end]+'\n\t{OM_OEM_PARAM_WEATHER_CAC_ENABLE,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,0,"wea_cac_en"},\n\t{OM_OEM_PARAM_WEATHER_CAC_ENABLE,0,IW_PRIV_TYPE_INT|IW_PRIV_SIZE_FIXED|1,"get_wea_cac_en"},'+text[end:]
    change(relative,text)
    (a.output/'weather478-recovery.patch').write_text(''.join(patch),encoding='utf-8',newline='\n')
    result={'status':'SOURCE_ONLY_WEATHER478_BOOLEAN_AP_SELECTION_PENDING_MODULE_GATES',
            'hardware_accessed':False,'firmware_eligible':False,'parent':str(a.parent),
            'parent_sha256':sha(a.parent/'result.json'),'source_original_records':34,
            'qualified_combined_records':None,'changed_sources':changes,
            'limits':['OEM boolean lowbyte and AP weather exclusion consumer recovered; table presence is not physical CAC acceptance.',
                      'Actual IC padding must be verified by ARC all-member witness before reuse.',
                      'Weather flag permits selection only; existing600-second weatherCAC, radar/CAC gating and channel/regulatory constraints remain unchanged.',
                      'Existing5GHz AP metric/alternate/fallback behavior retained; not complete OEM AP ranking equivalence.',
                      'No RF/client/traffic/persistence/release or hardware action.']}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'changed_files':len(changes),'source_sha256':sha(a.output/'result.json')}))


if __name__=='__main__':main()
