"""Current independent VOPT R9 source/caller/fixture review, no promotion."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from catalog_hgw_firmware_comments import scan_comments

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    parent=ROOT/'outputs/rea/consolidated32-source-20261022T222600Z-r2'
    source=ROOT/'outputs/rea/vopt34-linux-source-20261022T215800Z-r9'
    proof=json.loads((source/'result.json').read_text());assert proof['patch_scope']=='EXACT_R8_TO_R9_IC_OPMODE_481_ONLY'
    paths=[Path(__file__),source/'result.json'];comments={}
    for folder in('source','headers'):
        for old in(parent/folder).rglob('*'):
            if not old.is_file():continue
            new=source/old.relative_to(parent);assert new.is_file()
            before,after=old.read_bytes(),new.read_bytes()
            if before!=after and old.suffix in('.c','.h','.inc'):
                commentbytes=lambda raw:Counter(raw[r['offset']:r['end_offset']]for r in scan_comments(raw))
                missing=commentbytes(before)-commentbytes(after)
                comments[old.relative_to(parent).as_posix()]={'old':sum(commentbytes(before).values()),'missing':sum(missing.values())}
            paths.extend([old,new])
    adapter=(source/'source/wlan/openmitrastar_vopt481_kernel.inc').read_text()
    assert 'om_vopt_set(&ic->om_vopt,ic->ic_opmode' in adapter
    assert 'om_vopt_get(&ic->om_vopt,ic->ic_opmode' in adapter
    assert 'ic->ic_curchan->ic_maxpower_normal' in adapter
    assert 'rtnl_trylock()' in adapter and 'current_work()==&ic->om_vopt_work' in adapter
    assert 'case 232:case 375:' in adapter
    assert 'ic->ic_iterate_nodes(&ic->ic_sta,om_vopt_kernel_peer,counts,0)' in adapter
    core=(source/'source/wlan/openmitrastar_vopt481_kernel_core.inc').read_text()
    assert core.count('if(om482_rc==-115)return om482_rc;')==2
    host=(source/'source/qdrv/qdrv_hostlink.c').read_text()
    start=host.index('int om_qdrv_vopt482(struct ieee80211vap *vap')
    helper=host[start:]
    assert helper.index('qdrv_f355_claim("vopt482")')<helper.index('command=qdrv_hostlink_alloc_coherent')
    assert 'if(cal_rc==-EINPROGRESS)goto retained;'in helper
    assert 'if(normal_rc==-EINPROGRESS)goto retained;'in helper
    assert 'if(!published)return -EIO;'in host
    comm=(source/'source/qdrv/qdrv_comm.c').read_text()
    assert 'INIT_WORK(&qcb->comm_wq, comm_work)'in comm and 'schedule_work(&qcb->comm_wq)'in comm
    assert 'if(qdrv_vap_init(mac, hifinfo, mp->ioctl_arg1,'in comm
    for name,expected in [('vopt34-r9-root-worker-replay-20261022T222000Z-r1',270),
                          ('vopt34-r9-root-timer-owned-replay-20261022T222000Z-r1',3)]:
        path=ROOT/'outputs/rea'/name/'result.json';r=json.loads(path.read_text())
        assert r['status'].startswith('PASS_') and r['cases']==expected
        for file,digest in r['input_pins'].items():assert sha(file)==digest;paths.append(Path(file))
        paths.append(path)
    rows=[{'path':str(path),'sha256':sha(path)}for path in sorted(set(paths))]
    missing=sum(r['missing']for r in comments.values())
    result={'status':'PASS_ROOT_VOPT34_R9_SOURCE_CONTRACT_FIXTURES_PENDING_FULL_MODULES'if not missing else'NO_GO_OLD_COMMENTS_MISSING',
            'hardware_accessed':False,'firmware_eligible':False,'qualified_records_added':0,
            'source_sha256':sha(source/'result.json'),'old_comment_check':comments,
            'evidence_pins':rows,
            'limits':['Current mode481 uses named radioIC opmode; old R8 perVAP binding is not selected.',
                      'Worker270cases and fulltimer/owned482/F3553cases use fake scheduler/RTNL/MMIO.',
                      'HeaderABI witness retained +96hosttail; fullpaired build, sameheadercontrol, moduleglobal/residual/symbol/negative gates pending.',
                      'OptionalVSP get/set APIs absent in selected build; optional OEM skips retained, noVSP runtime proof.',
                      'Unknown482 retains descriptor/DMA/IC/module and blocks subsequent414/reassociation; no automatic recovery/unload claim.',
                      'No physicalRF/client/traffic/persistence/rollback/release acceptance.']}
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'missing_old_comments':missing,'pins':len(rows),'sha256':sha(a.output/'result.json')}))


if __name__=='__main__':main()
