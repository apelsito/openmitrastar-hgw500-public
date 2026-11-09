"""Independent current review of qualified32 plus bounded467 composition."""
import argparse
import hashlib
import json
from pathlib import Path
from audit_consolidated32_bounded467_modules import audit
from qualify_f370_qdrv_module import Elf

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    source=ROOT/'outputs/rea/consolidated32-plus-bounded467-source-20261022T231000Z-r1'
    parent=ROOT/'outputs/rea/consolidated32-source-20261022T222600Z-r2'
    pair=ROOT/'outputs/rea/consolidated32-plus-bounded467-pair-20261022T231200Z-r1'
    parent_pair=ROOT/'outputs/rea/consolidated32-pair-20261022T223400Z-r2'
    proof_path=ROOT/'outputs/rea/consolidated32-plus-bounded467-qualification-20261022T232300Z-r1/result.json'
    proof=json.loads(proof_path.read_text());assert proof['status']=='PASS_OFFLINE_CONSOLIDATED32_PLUS_ONE_BOUNDED467_SEVEN_MODULE_CHECKPOINT'
    assert proof['complete_original_records']==32 and proof['bounded_extra_records']==1 and not proof['allmode_oem467_recovery']
    allowed={'headers/net80211/ieee80211_var.h','source/wlan/ieee80211_wireless.c','source/wlan/ieee80211_scan.c','source/wlan/ieee80211_scan_ap.c'}
    changed=set();paths=[proof_path,Path(__file__)]
    for directory in ('source','headers'):
        old={str(f.relative_to(parent)).replace('\\','/'):f for f in(parent/directory).rglob('*')if f.is_file()}
        new={str(f.relative_to(source)).replace('\\','/'):f for f in(source/directory).rglob('*')if f.is_file()}
        assert set(old)==set(new)
        for relative in old:
            if sha(old[relative])!=sha(new[relative]):changed.add(relative)
            paths.extend([old[relative],new[relative]])
    assert changed==allowed
    for name in ('openmitrastar_chanset_recovered.h','openmitrastar_chanset_recovered.c','openmitrastar_chanset_kernel.inc','openmitrastar_chanset_tables.h'):
        assert sha(parent/'source/wlan'/name)==sha(source/'source/wlan'/name)
    for name in ('query','getter','policy461','negative'):
        dates={'query':'231300','getter':'231300','policy461':'231700','negative':'231900'}
        path=ROOT/f'outputs/rea/consolidated32-plus-bounded467-{name}-20261022T{dates[name]}Z-r1/result.json'
        receipt=json.loads(path.read_text());assert receipt['status'].startswith('PASS_');paths.append(path)
    reports={}
    for component in ('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
        old=parent_pair/'a-joint'/component/(component+'.ko')
        first=pair/'a-joint'/component/(component+'.ko');second=pair/'b-joint'/component/(component+'.ko')
        assert sha(first)==sha(second)
        if component in('wlan','wlan_scan_ap'):reports[component]=audit(Elf(old),Elf(first),component)
        else:assert sha(old)==sha(first)
        paths.extend([old,first,second])
    rows=[{'path':str(path),'sha256':sha(path)}for path in sorted(set(paths))]
    result={'status':'PASS_ROOT_INDEPENDENT_CONSOLIDATED32_PLUS_BOUNDED467_REVIEW',
            'hardware_accessed':False,'firmware_eligible':False,'allmode_oem467_recovery':False,
            'reconstructed_original_records':32,'bounded_extra_records':1,'private_table_records':599,
            'all_461_source_preserved':True,'evidence_pins':rows,'module_audits':reports,
            'limits':proof['bounded_limits']+['Counters denote recovered private records, not full functional driver features.']}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'review_pins':len(rows),'sha256':sha(a.output/'result.json')}))


if __name__=='__main__':main()
