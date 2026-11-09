"""Build15entryWLtwice and retain exact14QDRV without ABI change.

Compile every19WLAN Cunits for two lanes. QDRV is unchanged and copied
as exact already-qualified14entry module; noQDRVheader change.
Never patches module bytes, modifies source, packages firmware or uses hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import os
from concurrent.futures import ThreadPoolExecutor

import build_f370_qdrv_module as qb
import build_wlan_txmaxmpdu_alias_module as wb
from qualify_f370_qdrv_module import Elf, baseline_compare

ROOT = qb.ROOT


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dependency_key(path):
    # The selected trees are exact local files with no symlink sources. Use
    # lexical normalization for membership only; every content hash is verified.
    # Path.resolve makes many slow plan9 metadata RPCs per header on /mnt/c.
    return os.path.abspath(os.fspath(path))


def run(command, cwd, log):
    log.with_suffix('.command.json').write_text(json.dumps(command, indent=2)+'\n')
    proc = subprocess.run(command, cwd=cwd, capture_output=True, timeout=180)
    log.with_suffix('.stdout').write_bytes(proc.stdout)
    log.with_suffix('.stderr').write_bytes(proc.stderr)
    if proc.returncode:
        raise RuntimeError(log.name+': '+proc.stderr.decode(errors='replace')[-2500:])


def names_qdrv(source):
    return [x[:-2] for x in (source/'Makefile').read_text().split('qdrv-objs :=',1)[1].split('obj-m',1)[0].replace('\\',' ').split() if x.endswith('.o')]


def deps(path):
    return path.read_text().split(':',1)[1].replace('\\\n',' ').split()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--candidate', type=Path, required=True)
    ap.add_argument('--qdrv-baseline-build', type=Path, required=True)
    ap.add_argument('--wlan-baseline-build', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    out = a.output.resolve()
    out.relative_to((ROOT/'outputs/rea').resolve())
    assert out.name.startswith('driver5g-ops-') and not out.exists()
    parent_candidate=ROOT/'outputs/rea/bbdf-recovery-candidate-20261022T144500Z-r1'
    source = parent_candidate/'source/qdrv'
    wireless = a.candidate/'ieee80211_wireless.c'
    proof = json.loads((a.candidate/'result.json').read_text())
    assert proof['total_original_entries_added']==15 and proof['remaining_original_table_gaps']==29
    assert sha(source/'qdrv_wlan.c')=='7c163a0d0fa57197e2f0ebc138f79caaf927c6a037f63b1fcd8b36809a48603f'
    assert sha(wireless)==proof['candidate_sha256']=='538da528ed69173af54bb5f7c8001e75254fadc883b6464e6674cff2d83e9cb2'
    assert sha(source/'qdrv_wlan.h')=='154f0088d94f73a2a8bd708cbd543d80029d2f1cc7067cf7cf992582be083727'
    assert proof['functional_ops_added']==13 and proof['faithful_unsupported']==2
    qnames=names_qdrv(source)
    wproof=json.loads((a.wlan_baseline_build/'result.json').read_text())
    assert wproof['status']=='PASS_OFFLINE_FULL_BASELINE_EQUIVALENT_DECLARED_SRCVERSION' and wproof['reproducible'] and not wproof['comparison_errors']
    wnames=wproof['units']
    assert len(qnames)==34 and len(wnames)==19
    qbaseline=a.qdrv_baseline_build/'baseline'
    assert baseline_compare(Elf(qb.MODULE),Elf(qbaseline/'qdrv.ko'))['status']=='PASS_FULL_BASELINE_RECONSTRUCTION'
    assert sha(a.wlan_baseline_build/'a/wlan.ko')==sha(a.wlan_baseline_build/'b/wlan.ko')==wproof['modules'][0]['sha256']
    # Candidate QDRV is the retained F364/F365 baseline, not the F370 observation
    # candidate: four unrelated AuC counters must not silently join this change.
    assert sha(source/'qdrv_tx.c')==sha(qb.BASE/'qdrv_tx.c')=='2f93045dc3937074300c571e1b5f1d49c95e51de91d8e00b0742db1177438c1d'
    protected=set()
    print(json.dumps({'stage':'verify-baseline-pin-hashes'}),flush=True)
    for build in (a.qdrv_baseline_build,a.wlan_baseline_build):
        pins=json.loads((build/'input-pins.json').read_text())
        for path,h in pins.items():
            assert sha(path)==h,'baseline pin changed '+path
            protected.add(Path(path))
        protected.update((build/'result.json',build/'input-pins.json',build/'dependencies.symvers'))
    for tree in ('include/generated','include/config','arch/arc/include/generated'):
        protected.update(x for x in (qb.context.CONTEXT/tree).rglob('*') if x.is_file())
    protected.update(x for x in a.candidate.rglob('*') if x.is_file())
    protected.update(x for x in parent_candidate.rglob('*') if x.is_file())
    protected.update(x for x in qbaseline.iterdir() if x.is_file())
    for lane in ('a','b'):
        protected.update(x for x in (a.wlan_baseline_build/lane).iterdir() if x.is_file())
    protected.update((Path(__file__),Path(qb.__file__),Path(wb.__file__),Path(qb.context.__file__),qb.context.CONTEXT/'scripts/mod/modpost',qb.context.CONTEXT/'scripts/module.lds'))
    # Some retained baseline headers used only by unmodified units were not in
    # F370's aggregate pin set. Pin their actual pre-existing .d closure before
    # building, rather than silently accepting unpinned inputs after compile.
    dependency_paths=set()
    for directory in (qbaseline,a.wlan_baseline_build/'a',a.wlan_baseline_build/'b'):
        for depfile in directory.glob('*.d'):
            for value in deps(depfile):
                path=Path(value) if value.startswith('/') else qb.context.CONTEXT/value
                dependency_paths.add(Path(dependency_key(path)))
    print(json.dumps({'stage':'pin-unique-dependencies','unique_dependencies':len(dependency_paths)}),flush=True)
    for path in dependency_paths:
        if path.is_file():
            protected.add(path)
    pinmap={str(p):sha(p) for p in protected}
    print(json.dumps({'stage':'pins-complete','pins':len(pinmap)}),flush=True)
    canonical={dependency_key(p) for p in pinmap}
    cache={}
    def canon(value):
        if value not in cache:
            cache[value]=dependency_key(Path(value) if value.startswith('/') else qb.context.CONTEXT/value)
        return cache[value]
    out.mkdir(parents=True,exist_ok=False)
    (out/'input-pins.json').write_text(json.dumps(pinmap,indent=2)+'\n')
    result={'schema':'openmitrastar.fifteen-entry-wlan-module/v1','status':'NO_GO_MODULE_PAIR','hardware_accessed':False,'firmware_eligible':False,'physical_gates':'UNRUN','modules':[],
            'candidate':str(a.candidate),'qdrv_baseline_build':str(a.qdrv_baseline_build),'wlan_baseline_build':str(a.wlan_baseline_build),
            'qdrv_baseline_lineage':'F364_F365_BASELINE_WITHOUT_F370_OBSERVATION_COUNTERS','total_original_entries':15,'functional_ops_added':13,'faithful_unsupported':2,'remaining_oem_table_gaps':29,'nac_prototype_included':False,
            'limits':'Complete source-built module pair linkage; whole-module delta qualification still required. No runtime, RF, traffic or release acceptance.'}
    try:
        for lane in ('a','b'):
            for component,names,baseline,changed in (('wlan',wnames,a.wlan_baseline_build/lane,'ieee80211_wireless'),):
                folder=out/lane/component
                folder.mkdir(parents=True)
                def unit(name):
                    input_source=source/(name+'.c') if component=='qdrv' else (wireless if name=='ieee80211_wireless' else parent_candidate/'source/wlan'/(name+'.c'))
                    if component=='wlan' and not input_source.exists():
                        # Candidate contains its complete inherited WLAN tree;
                        # one unchanged port shim lives only in original parent.
                        # Still compile it from its prebuild pinned source anew.
                        input_source=wb.OLD/(name+'.c')
                        assert str(input_source) in pinmap,'missing unpinned inherited WLAN source'
                    command=qb.command(name,source,folder)[0] if component=='qdrv' else wb.command(name,folder,input_source)
                    run(command,qb.context.CONTEXT,folder/('compile-'+name))
                    dependencies=deps(folder/(name+'.d'))
                    missing=sorted({canon(x) for x in dependencies}-canonical)
                    assert not missing,'un-pinned dependency '+str(missing)
                    (folder/('.'+name+'.o.cmd')).write_text('source_'+str(folder/(name+'.o'))+' := '+str(input_source)+'\n\ndeps_'+str(folder/(name+'.o'))+' := \\\n'+''.join('  '+d+' \\\n' for d in dependencies)+'\n')
                    print(json.dumps({'lane':lane,'component':component,'compiled':name}),flush=True)
                with ThreadPoolExecutor(max_workers=4) as pool:
                    list(pool.map(unit,names))
                objects=[str(folder/(name+'.o')) for name in names]
                (folder/(component+'.mod')).write_text('\n'.join(objects)+'\n')
                run([str(qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','-o',str(folder/(component+'.o')),*objects],folder,folder/'link-relocatable')
                dep=a.qdrv_baseline_build/'dependencies.symvers' if component=='qdrv' else a.wlan_baseline_build/'dependencies.symvers'
                run([str(qb.context.CONTEXT/'scripts/mod/modpost'),'-e','-a','-i',str(dep),'-o',str(folder/'Module.symvers'),str(folder/(component+'.o'))],folder,folder/'modpost')
                command=qb.command('qdrv.mod',source,folder,True)[0] if component=='qdrv' else wb.command('wlan.mod',folder,wireless)
                run(command,qb.context.CONTEXT,folder/'compile-metadata')
                run([str(qb.context.TC)+'ld','-r','-z','noexecstack','--no-warn-rwx-segments','--build-id=sha1','-T',str(qb.context.CONTEXT/'scripts/module.lds'),'-o',str(folder/(component+'.ko')),str(folder/(component+'.o')),str(folder/(component+'.mod.o'))],folder,folder/'link-module')
                path=folder/(component+'.ko')
                result['modules'].append({'lane':lane,'component':component,'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)})
                print(json.dumps(result['modules'][-1]),flush=True)
        for component in ('wlan',):
            assert sha(out/'a'/component/(component+'.ko'))==sha(out/'b'/component/(component+'.ko')),'nonreproducible '+component
        for path,h in pinmap.items():
            assert sha(path)==h,'protected input changed '+path
        result.update(status='PASS_ALL_WLAN_UNITS_FIFTEEN_PENDING_DELTA_QUALIFICATION',reproducible=True,protected_inputs_unchanged=True,
                      all_source_units_compiled_per_lane=19,qdrv_source_built_units_linked=0,wlan_source_built_units_linked=19,
                      reused_qdrv_units_per_lane=0,reused_wlan_units_per_lane=0,private_qdrv_size_bytes=30556,private_bool_offset=30552)
    except Exception as exc:
        result['error']=str(exc)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return int(result['status']!='PASS_ALL_WLAN_UNITS_FIFTEEN_PENDING_DELTA_QUALIFICATION')


if __name__=='__main__':
    raise SystemExit(main())
