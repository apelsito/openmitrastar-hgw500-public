"""Read-only independent current weather478 source/module/ABI review."""
import argparse
import hashlib
import json
from pathlib import Path
from audit_hgw5g_weather478_modules import audit
from qualify_f370_qdrv_module import Elf

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    source=ROOT/'outputs/rea/weather478-source34-20261022T210000Z-r1'
    parent=ROOT/'outputs/rea/consolidated32-source-20261022T222600Z-r2'
    pair=ROOT/'outputs/rea/weather478-pair-20261022T234500Z-r1'
    oldpair=ROOT/'outputs/rea/consolidated32-pair-20261022T223400Z-r2'
    paths=[Path(__file__),source/'result.json',pair/'result.json']
    cp=json.loads((source/'result.json').read_text());assert cp['source_original_records']==34
    allowed={'headers/net80211/ieee80211_var.h','source/qdrv/qdrv_wlan.c','source/wlan/ieee80211_scan_ap.c','source/wlan/ieee80211_wireless.c'}
    changed=set()
    for folder in ('source','headers'):
        for x in(parent/folder).rglob('*'):
            if not x.is_file():continue
            relative=x.relative_to(parent);y=source/relative
            assert y.is_file()
            if sha(x)!=sha(y):changed.add(relative.as_posix())
            paths.extend([x,y])
    assert changed==allowed
    radar=source/'source/qdrv/qdrv_radar.c'
    assert sha(radar)==sha(parent/'source/qdrv/qdrv_radar.c')
    text=radar.read_text();assert '#define CAC_WEATHER_PERIOD_EU\t(600 * HZ)'in text
    assert 'expires = jiffies + CAC_WEATHER_PERIOD_EU;'in text
    ap=(source/'source/wlan/ieee80211_scan_ap.c').read_text()
    assert '!READ_ONCE(ic->om_weather_cac_enabled) &&\n\t\t    ieee80211_is_on_weather_channel(ic, ic_best_chan)'in ap
    old=(parent/'headers/net80211/ieee80211_var.h').read_text()
    new=(source/'headers/net80211/ieee80211_var.h').read_text()
    assert new.replace(' u8 om_weather_cac_enabled; /* OEM478: former padding. */','')==old
    abi_path=ROOT/'outputs/rea/weather478-all-abi-20261022T234000Z-r1/result.json'
    abi=json.loads(abi_path.read_text());assert abi['status']=='PASS_ARC_WEATHER478_ALL_OLD_FIELDS_WIRE_SIZES_FORMER_PADDING22605'
    assert abi['host_delta']==0 and abi['rows'][0]['sizes']==abi['rows'][1]['sizes']
    for typ in ('ieee80211com','ieee80211vap','qdrv_wlan'):
        assert abi['rows'][0]['fields'][typ]==abi['rows'][1]['fields'][typ]
    paths.append(abi_path)
    for name,expected in [('weather478-actual-consumers-20261022T210300Z-r2','PASS_WEATHER478_ACTUAL_AP_POLICY_AND_WEXT_SOURCE_CONSUMERS'),
                          ('weather478-default-proof-20261022T235200Z-r1','PASS_WEATHER478_OEM_ZERO_INIT_BOOLEAN_AP_SOURCE_DEFAULT_FRAGMENTS'),
                          ('weather478-negative-20261022T235700Z-r2','PASS_SIXTEEN_WEATHER478_PARSED_NEGATIVE_DELTA_CASES')]:
        path=ROOT/'outputs/rea'/name/'result.json';r=json.loads(path.read_text());assert r['status']==expected;paths.append(path)
    reports={}
    for component in ('qdrv','wlan','wlan_scan_ap','wlan_scan_sta','wlan_ccmp','wlan_tkip','wlan_xauth'):
        x=oldpair/'a-joint'/component/(component+'.ko');y=pair/'a-joint'/component/(component+'.ko');z=pair/'b-joint'/component/(component+'.ko')
        assert sha(y)==sha(z)
        if component in('qdrv','wlan','wlan_scan_ap'):reports[component]=audit(Elf(x),Elf(y),component)
        else:assert sha(x)==sha(y)
        paths.extend([x,y,z])
    rows=[{'path':str(path),'sha256':sha(path)}for path in sorted(set(paths))]
    result={'status':'PASS_ROOT_INDEPENDENT_WEATHER478_SOURCE34_MODULE_REVIEW',
            'hardware_accessed':False,'firmware_eligible':False,'reconstructed_records':34,
            'remaining_original_records':10,'private_table_records':600,
            'old_ABI_sizes_and_fields_unchanged':True,'weather_CAC_radar_source_unchanged':True,
            'evidence_pins':rows,'module_audits':reports,
            'limits':['Record recovery with actual policy/source consumers and paired modules; not34 fullfeatures.',
                      'Actual AP fixture20MHz with fake callbacks; metric/alternate/fallback and other widths retain prior scope.',
                      'Weather selection does not shorten600-second weatherCAC, clear radar, complete CAC or establish regulatory/calibration/RF acceptance.',
                      'Default0 constructor fragments and whole allocation zero are observed; indirect asynchronous constructor consumers not universally replayed.',
                      'No hardware/RF/client/traffic/persistence/rollback/release acceptance.']}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'pins':len(rows),'sha256':sha(a.output/'result.json')}))


if __name__=='__main__':main()
