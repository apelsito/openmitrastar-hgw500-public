"""Recover OEM457 NAC records from qualified20 without new host/wire ABI.

Setter retains OEM HOSTAP-only forwarding and successful no-op in other modes.
Getter samples only8-byte published prefix with guarded missing/zero state.
MuC updates may race between scalar reads: this is not a coherent snapshot.
No cliententry/calibration/opaque tail export, nohardware ormonitor activation.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

HELPER='''/* ExactOEM457sharedprefixsample. F355retains the owning sharedallocation
 * after core-start; WEXTVAP access follows that start. No entry/clientdata read.
 * Scalarreads can span MuCupdates, so no coherent generation is asserted.
 * Guard zero-initialized/not-ready state rather than reproducing OEMdivision0. */
struct om_nac_prefix {u16 value0;u16 value1;u16 enabled;u16 reserved;};
static int om_nac_prefix_sample(struct om_nac_prefix *nac,int *value)
{
    u16 first,second;
    u8 enabled;
    u32 percent;
    if(!nac)return -EAGAIN;
    first=READ_ONCE(nac->value0);
    second=READ_ONCE(nac->value1);
    enabled=(u8)READ_ONCE(nac->enabled);
    if(!second)return -EAGAIN;
    percent=((u32)first*100U)/second;
    *value=((u32)second<<16)|((percent&255U)<<8)|enabled;
    return 0;
}

'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 parent=json.loads((a.parent/'result.json').read_text());assert parent['total_original_entries_added']==20
 a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers')
 path=a.output/'source/wlan/ieee80211_wireless.c';original=path.read_text();new=original.replace('#define OM_OEM_PARAM_DEVICE_MODE 451','#define OM_OEM_PARAM_NAC_MODE 457\n#define OM_OEM_PARAM_DEVICE_MODE 451',1)
 anchor='static int\nieee80211_ioctl_getparam(';start=new.index(anchor);new=new[:start]+HELPER+new[start:]
 start=new.index('ieee80211_ioctl_setparam(struct net_device *dev, struct iw_request_info *info,');brace=new.index('{',new.index('switch (param)',start))
 setter='''
\tcase OM_OEM_PARAM_NAC_MODE:
\t\t/* OEMnon-HOSTAPcase is a successfulno-op; no mode activation here. */
\t\tif(vap->iv_opmode == IEEE80211_M_HOSTAP)
\t\t\tieee80211_param_to_qdrv(vap,param,value,NULL,0);
\t\tbreak;
''';new=new[:brace+1]+setter+new[brace+1:]
 start=new.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=new.index('{',new.index('switch (param[0] & 0xffff)',start))
 getter='''
\tcase OM_OEM_PARAM_NAC_MODE:
\t\t{
\t\t\tstruct shared_params *shared=READ_ONCE(soc_shared_params);
\t\t\tif(!shared)return -EAGAIN;
\t\t\treturn om_nac_prefix_sample(
\t\t\t    (struct om_nac_prefix *)READ_ONCE(shared->nac_mon_info_lhost),
\t\t\t    &param[0]);
\t\t}
''';new=new[:brace+1]+getter+new[brace+1:]
 start=new.index('static const struct iw_priv_args ieee80211_priv_args[]');end=new.index('\n};',start);entries='\n\t{ OM_OEM_PARAM_NAC_MODE,\n\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,0,"nac_mode" },\n\t{ OM_OEM_PARAM_NAC_MODE,\n\t  0,IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,"get_nac_mode" },';new=new[:end]+entries+new[end:]
 path.write_text(new,newline='\n');(a.output/'nac22.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),new.splitlines(True),fromfile='a/src/wlan/ieee80211_wireless.c',tofile='b/src/wlan/ieee80211_wireless.c')),newline='\n')
 result=dict(status='SOURCE_ONLY_NAC22_RECONSTRUCTED_RECORDS_NO_GO_MODULE',hardware_accessed=False,firmware_eligible=False,parent=str(a.parent),parent_manifest_sha256=sha(a.parent/'result.json'),parent_wireless_sha256=hashlib.sha256(original.encode()).hexdigest(),wireless_sha256=sha(path),total_original_entries_added=22,remaining_original_table_gaps=22,records_added=[dict(id=457,name='nac_mode',semantics='ExactHOSTAPforward/nonAPno-op'),dict(id=457,name='get_nac_mode',semantics='OEMpacking sampledtuple; EAGAINmissing/denominator0safetydelta')],header_unchanged=True,limits=['Not22fullyacceptedfeatures: twolegacyunsupported andNACgetter incoherenttuple','Sharedallocationlifecycle F355/VAPbounds mustremainqualified','NoMuCtimer/monitor/client/trafficphysicalacceptance','NoadditionalprivateAPIorwireABIchange'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
