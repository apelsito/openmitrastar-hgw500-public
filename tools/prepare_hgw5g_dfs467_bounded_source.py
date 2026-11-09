"""Bounded 5GHz initialized-scanner recovery of exact OEM467 query sequence.

Original callback (QDRVtext+0x2740c) refreshes scan-list through scanner start,
then picks with 0x130000 and returns1 or-EOPNOTSUPP. Preserve current port's
metric/alternate machinery; add only exactDFSflagfilter to that provider.
Explicitly refuse24GHzmode branch owned bymissing461; neveraliasboolCACquery.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

HELPER='''/* OEM467: scanner-list refresh then pick0x130000, return1/-95.
 * This bounded recovery admits initialized AP scanner in 5GHz modes only.
 * OEM24GHz modes2/3/8/9 delegate to the separate chanset461 algorithm.
 * Existing port metric/alternate paths remain; no alias to CAC-readybool.
 * scan_start here is scanner policy/list construction, not RF scan_start. */
int om_ieee80211_dfs_channel_available(struct ieee80211com *ic)
{
    struct ieee80211_scan_state *ss=READ_ONCE(ic->ic_scan);
    const struct ieee80211_scanner *ops;
    struct ieee80211vap *vap;
    struct ieee80211_channel *picked;
    int mode=READ_ONCE(ic->ic_phymode);
    if(mode!=1&&mode!=7&&mode!=10&&(unsigned)(mode-11)>=4U)
        return -EOPNOTSUPP;
    if(!ss)return -EOPNOTSUPP;
    ops=READ_ONCE(ss->ss_ops);
    vap=READ_ONCE(ss->ss_vap);
    if(!ops||!vap||!ss->ss_priv||vap->iv_opmode!=IEEE80211_M_HOSTAP)
        return -EOPNOTSUPP;
    /* Missing scannerstart originally left the oldlist inplace. Refuse that
     * incomplete path so no success is returned from a stale partial list. */
    if(!ops->scan_start||!ops->scan_pickchan)return -EOPNOTSUPP;
    ops->scan_start(ss,vap);
    picked=ieee80211_scan_pickchannel(ic,0x130000);
    return picked?1:-EOPNOTSUPP;
}
EXPORT_SYMBOL(om_ieee80211_dfs_channel_available);

'''

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();pp=json.loads((a.parent/'result.json').read_text());assert pp['combined_source_records']==29;a.output.mkdir(parents=True,exist_ok=False);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');changes={};patch=[]
 def change(rel,new):
  path=a.output/rel;old=path.read_text();path.write_text(new,newline='\n');changes[rel]=sha(path);patch.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 rel='headers/net80211/ieee80211_var.h';old=(a.output/rel).read_text();needle='void ieee80211_pm_queue_work(struct ieee80211com *ic);';assert old.count(needle)==1;new=old.replace(needle,needle+' int om_ieee80211_dfs_channel_available(struct ieee80211com *ic);',1);assert len(old.splitlines())==len(new.splitlines());change(rel,new)
 rel='source/wlan/ieee80211_scan.c';old=(a.output/rel).read_text();needle='int ieee80211_get_type_of_neighborhood(';assert old.count(needle)==1;change(rel,old.replace(needle,HELPER+needle,1))
 rel='source/wlan/ieee80211_scan_ap.c';old=(a.output/rel).read_text();needle='\t\t/* IEEE80211_SCAN_PICK_NOT_AVAILABLE_DFS_ONLY is set only during ICAC */';assert old.count(needle)==1;new=old.replace(needle,'''\t\t/* Exact OEM467 selector flag13 admits DFS-only after channel validation.
\t\t * It intentionally does not mean not-yet-CAC or available-only. */
\t\tif (flags == 0x130000 && !(ic_best_chan->ic_flags & IEEE80211_CHAN_DFS))
\t\t\tcontinue;

'''+needle,1);change(rel,new)
 rel='source/wlan/ieee80211_wireless.c';old=(a.output/rel).read_text();new=old.replace('#define OM_OEM_PARAM_COC_MOVE_NDFS 491','#define OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE 467\n#define OM_OEM_PARAM_COC_MOVE_NDFS 491',1);start=new.index('ieee80211_ioctl_getparam(struct net_device *dev, struct iw_request_info *info,');brace=new.index('{',new.index('switch (param[0] & 0xffff)',start));new=new[:brace+1]+'''\n\tcase OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE:
\t\tparam[0]=om_ieee80211_dfs_channel_available(ic);
\t\treturn 0;
'''+new[brace+1:];start=new.index('static const struct iw_priv_args ieee80211_priv_args[]');end=new.index('\n};',start);new=new[:end]+'''\n\t{ OM_OEM_PARAM_DFS_CHANNEL_AVAILABLE,0,
\t  IW_PRIV_TYPE_INT | IW_PRIV_SIZE_FIXED | 1,"dfs_chan_avail" },'''+new[end:];change(rel,new)
 (a.output/'dfs467-bounded-recovery.patch').write_text(''.join(patch),newline='\n');result=dict(status='SOURCE_ONLY_DFS467_5GHZ_INITIALIZED_SCANNER_PENDING_GATES',hardware_accessed=False,firmware_eligible=False,parent=str(a.parent),parent_manifest_sha256=sha(a.parent/'result.json'),candidate_private_record_added=1,combined_source_records=30,qualified_combined_records=None,changed_sources=changes,host_layout_changed=False,header_old_line_positions_preserved=True,exact_sequence='scanner.scan_start(ss,vap) policyrefresh, scan_pickchannel(ic,0x130000), value1/-95, WEXTreturn0',exact_flag='DFSonly afterexistingcheckchannel; noavail/CACcompletedcriterion',safety_deviations=['24GHz/OEM461modes2/3/8/9 andunsupportedmodes return-95','Missingstart/pick/private/scannervap refuses stalequery insteadOEMpartiallistfallback','APscannerinitializedonly; noSTA/mixedscannerclaim'],limits=['Preservesretainedportmetric/alternate/width/fallbackmachinery; notfullOEMAPpickinstructionequivalence.','No24GHzchanset461implementationorallmode467acceptance.','NoPHY/RF/regulatory/calibration/clienttrafficpersistence/releaseacceptance.'])
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
