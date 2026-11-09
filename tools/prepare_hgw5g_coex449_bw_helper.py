"""Retain standalone OEM change_bw reconstruction before Source26 integration."""
import argparse
import hashlib
import json
from pathlib import Path

HELPER='''/* Recovered OEM change_bw (0x3412c,88 bytes) and its power helper
 * (0x2ef34,212 bytes). Operative order is BW71 wire, active-channel map,
 * existing regulatory/power table selection, optional set_channel callback.
 * This helper does not create regulatory entries or change calibration.
 * Existing void callbacks cannot establish completed PHY/MuC transitions. */
void om_ieee80211_change_bw(struct ieee80211vap *vap,int bw,int delay_ch_switch)
{
    struct ieee80211com *ic=vap->iv_ic;
    struct ieee80211_channel *chan;
    int idx;
    int i;
    ieee80211_param_to_qdrv(vap,IEEE80211_PARAM_BW_SEL_MUC,bw,NULL,0);
    switch(bw){
    case BW_HT40:
        memcpy(ic->ic_chan_active,ic->ic_chan_active_40,sizeof(ic->ic_chan_active));
        break;
    case BW_HT80:
        memcpy(ic->ic_chan_active,ic->ic_chan_active_80,sizeof(ic->ic_chan_active));
        break;
    default:
        memcpy(ic->ic_chan_active,ic->ic_chan_active_20,sizeof(ic->ic_chan_active));
        break;
    }
    if(ic->ic_country_code!=CTRY_DEFAULT){
        switch(bw){
        case BW_HT20:idx=PWR_IDX_20M;break;
        case BW_HT40:idx=PWR_IDX_40M;break;
        case BW_HT80:idx=PWR_IDX_80M;break;
        default:
            printk("unsupported bw: %u\\n",bw);
            goto set_channel;
        }
        for(i=0;i<ic->ic_nchans;i++){
            chan=&ic->ic_channels[i];
            if(!isset(ic->ic_chan_active,chan->ic_ieee))continue;
            chan->ic_maxpower=chan->ic_maxpower_table[PWR_IDX_BF_OFF][PWR_IDX_1SS][idx];
            chan->ic_maxpower_normal=chan->ic_maxpower;
        }
    }
set_channel:
    if(!delay_ch_switch)ic->ic_set_channel(ic);
}
'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);path=a.output/'om_coex449_change_bw.c';path.write_text(HELPER,newline='\n');result=dict(status='SOURCE_RECOVERED_CHANGE_BW_TRANSACTION_PENDING_FIXTURE_ARC',hardware_accessed=False,firmware_eligible=False,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),oem_entries=['0x3412c:change_bw88B','0x2ef34:channel_power212B','0x6e55c:active_chanlist72B'],parameter=71,admitted_bandwidths=[20,40,80],unsupported_oem_contract='wire and20map stillapplied; nondefaultcountry unsupported logs thenoptionalsetchannel; nocountry simplymap+optionalsetchannel',limits='Standalonehelper notintegratedmodule; noPHY/MuC/regulatory/traffic acceptance');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
