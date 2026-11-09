"""Copy the current7.3 source package and portable tools to the private repo.

Immutable source/evidence copies, no device/private identity/binary artifacts.
Previous src baseline remains intact; current7.3 lives in a dedicated folder.
"""
import argparse
import hashlib
import json
from pathlib import Path
from preserve_hgw5g_progress_20261022_r13 import ROOT,REPO,ROWS,copy


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True)
    args=parser.parse_args();candidate=args.candidate.resolve()
    manifest=REPO/'manifests/preservation-checkpoint-20261022-linux73-private-source-r13.json'
    assert not manifest.exists()
    proof=json.loads((candidate/'result.json').read_text())
    for relative,digest in proof['files'].items():
        source=candidate/relative.replace('\\','/')
        assert source.is_file()and sha(source)==digest,'candidate inputdrift '+relative
    for group in('source','headers','kernel-overlay','providers'):
        for source in sorted((candidate/group).rglob('*')):
            if source.is_file():
                assert source.suffix.lower()not in('.o','.ko','.elf','.exe','.key','.pem','.bin')
                copy(source,Path('src/linux-7.3')/source.relative_to(candidate))
    for name in('Kbuild','result.json','kernel73-overlay.patch','linux73-api-fix.patch','sysctl-legacy-provenance.c.txt'):
        if(candidate/name).exists():copy(candidate/name,Path('src/linux-7.3')/name)
    copy(ROOT/'tools/linux73_build.py',Path('tools/linux73_build.py'))
    copy(ROOT/'docs/LINUX73_AELITA_BUILD.md',Path('docs/LINUX73_AELITA_BUILD.md'))
    tool_names=('prepare_hgw5g_linux73_candidate.py','compose_hgw5g_linux73_full44.py',
                'build_hgw5g_linux73_probe.py','fix_hgw5g_linux73_hostlink_api.py',
                'fix_hgw5g_linux73_binattr.py','fix_hgw5g_linux73_timers_files.py',
                'fix_hgw5g_linux73_optional_bus.py','fix_hgw5g_linux73_tx_trace_api.py',
                'fix_hgw5g_linux73_napi_api.py','fix_hgw5g_linux73_qdisc_stats.py',
                'fix_hgw5g_linux73_rtnetlink_header.py','fix_hgw5g_linux73_sysctl_api.py',
                'prepare_linux73_private_provider_overlay.py','prepare_linux73_narrow_platform_provider.py',
                'test_linux73_actual_aes_adapter.py','test_linux73_compat_controllers.py',
                'prepare_hgw5g_all_ops_source.py','prepare_hgw5g_all_ops_source_r2.py')
    for name in tool_names:copy(ROOT/'tools'/name,Path('tools/integration/linux73-r13')/name)
    folders=('linux73-providers-ccmp-qualification-20261022T211400Z-r1',
             'linux73-portable-build-plancheck-20261022T211800Z-r1',
             'linux73-full44-62c-compile-receipt-20261022T235000Z-r13',
             'hgw5g-all-ops-mdie-fixture-20261022T210200Z-r1',
             'hgw5g-all-ops-rbs-fixture-20261022T210200Z-r1',
             'hgw5g-all-ops-vopt-fixture-20261022T210200Z-r1')
    for name in folders:
        folder=ROOT/'outputs/rea'/name
        for source in sorted(folder.iterdir()):
            if source.is_file()and source.suffix in('.json','.md','.c','.h','.py','.txt'):
                copy(source,Path('evidence')/name/source.name)
    for row in ROWS:
        assert sha(ROOT/row['source'])==row['sha256']and sha(REPO/row['path'])==row['sha256']
    result={'schema':'openmitrastar.preservation-checkpoint/v1','files':ROWS,
            'hardware_accessed':False,'target_kernel':'Linux7.3','repository_visibility':'private',
            'source_package':str(candidate),'linux73_compiled_source_units':62,
            'linux73_module_pair_pass':False,'physical_driver_acceptance':False,
            'limits':'Exactsourcecopy+portabletool. Fullnewkernel/base/moduleclosure and physical gates remain.'}
    manifest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'files':len(ROWS),'bytes':sum(r['bytes']for r in ROWS),'all_copies_exact':True}))


if __name__=='__main__':main()
