"""Independent current-source/module review for the stated bounded467 scope."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from audit_hgw5g_dfs467_modules import audit
from qualify_f370_qdrv_module import Elf

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    source=ROOT/'outputs/rea/dfs467-bounded-source-20261022T225000Z-r2'
    old=ROOT/'outputs/rea/consolidated29-full-pair-20261022T214100Z-r2/a-joint'
    first=ROOT/'outputs/rea/dfs467-bounded-joint-a-20261022T225300Z-r2'
    second=ROOT/'outputs/rea/dfs467-bounded-joint-b-20261022T225300Z-r2'
    wire=(source/'source/wlan/ieee80211_wireless.c').read_text()
    scan=(source/'source/wlan/ieee80211_scan.c').read_text()
    query=scan[scan.index('int om_ieee80211_dfs_channel_available('):scan.index('EXPORT_SYMBOL(om_ieee80211_dfs_channel_available)')]
    assert query.index('ops->scan_start(ss,vap)')<query.index('if(!ss->ss_last')<query.index('ieee80211_scan_pickchannel(ic,0x130000)')
    assert 'ic_dfs_chans_available_for_cac'not in query
    assert 'param[0]=om_ieee80211_dfs_channel_available(ic);\n\t\treturn 0;'in wire
    assert query.count('vap->iv_opmode!=IEEE80211_M_HOSTAP')==1
    ap=(source/'source/wlan/ieee80211_scan_ap.c').read_text()
    assert 'flags == 0x130000 && !(ic_best_chan->ic_flags & IEEE80211_CHAN_DFS)'in ap
    receipt=ROOT/'outputs/rea/dfs467-root-independent-actual-pick-20261022T202000Z-r1/result.json'
    fixture=json.loads(receipt.read_text());assert fixture['cases']==28672 and fixture['missing_mode_cases']==96
    reports={}
    modules=[]
    for component in ('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
        x=old/component/(component+'.ko');y=first/component/(component+'.ko');z=second/component/(component+'.ko')
        assert sha(y)==sha(z)
        if component in('wlan','wlan_scan_ap'):reports[component]=audit(Elf(x),Elf(y),component)
        else:assert sha(x)==sha(y)
        modules.extend([x,y,z])
    for name in ('windows-oem-dfs467-callback-20261022T223300Z-r2','windows-oem-dfs467-refresh-20261022T223500Z-r1'):
        d=ROOT/'outputs/rea'/name;r=json.loads((d/'result.json').read_text())
        assert r['exit_code']==0 and r['target_unchanged'] and sha(d/'rea.json')==r['rea_output_sha256']
    paths=[Path(__file__).resolve(),receipt,*modules,
           *[source/rel for rel in ('result.json','source/wlan/ieee80211_scan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c','headers/net80211/ieee80211_var.h')],
           ROOT/'tools/audit_hgw5g_dfs467_modules.py',
           ROOT/'outputs/rea/dfs467-bounded-negative-20261022T225500Z-r1/result.json']
    evidence=[{'path':str(path),'sha256':sha(path)}for path in paths]
    result={'status':'PASS_ROOT_INDEPENDENT_DFS467_BOUNDED_STABLE_5GHZ_SOURCE_MODULE_REVIEW',
            'hardware_accessed':False,'firmware_eligible':False,
            'allmode_oem467_recovery':False,'promote_full_original_record_count':False,
            'evidence_pins':evidence,'module_audits':reports,
            'actual_source_fixture_cases':28672,'missing_mode_cases':96,
            'limits':['Only stable initialized AP scanner in admitted5GHz modes,20MHz deterministic fixture with declared fake callbacks.',
                      'Complete OEM AP metric/alternate/fallback equivalence and40/80MHz behavior remain unproved.',
                      'ANYC fallback may return first nonDFS entry; no general DFScapability or CACready claim.',
                      'Overlapping scans/hotdetach are excluded from this bounded receipt; live-query serialization still required before deployment.',
                      '464 host state/CAC callbacks untouched; no radio/runtime/firmware operation.',
                      'This review qualifies only the explicitly bounded source/module contract and cannot close full467 recovery.']}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'evidence_pins':len(evidence),'sha256':sha(a.output/'result.json')}))


if __name__=='__main__':main()
