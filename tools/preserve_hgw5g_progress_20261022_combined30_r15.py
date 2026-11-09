"""Seal the qualified combined30 and source-only scanner r15 in the repo."""
from pathlib import Path
import hashlib
import json
from preserve_hgw5g_progress_20261022_r13 import ROOT, REPO, ROWS, SOURCE_EXT, EVIDENCE_EXT, copy


def main():
    manifest = REPO / 'manifests/preservation-checkpoint-20261022-consolidated30-chanset-r15-r1.json'
    assert not manifest.exists(), 'already sealed'
    qualified = ROOT / 'outputs/rea/consolidated30-global-checkpoint-20261022T222200Z-r2/result.json'
    proof = json.loads(qualified.read_text())
    assert proof['status'] == 'PASS_OFFLINE_CONSOLIDATED30_R2_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT'
    assert proof['offline_original_records_reconstructed'] == 30 and proof['remaining_original_records'] == 14
    assert hashlib.sha256(qualified.read_bytes()).hexdigest() == '201dd5fffc1cf2ad0c2a50c94fe2d240615a0d97aac69a8b38a8214f3a35fcad'
    for name in ('consolidated30-source-20261022T221100Z-r2',
                 'chanset461-kernel-adapter-20261022T193500Z-r15'):
        folder = ROOT / 'outputs/rea' / name
        for source in sorted(folder.rglob('*')):
            if source.is_file() and (source.suffix in SOURCE_EXT or source.name in {'Makefile', 'Kconfig'}):
                copy(source, Path('candidates') / name / source.relative_to(folder))
    names = ('consolidated30-global-checkpoint-20261022T222200Z-r2',
             'consolidated30-incremental-20261022T221200Z-r2',
             'consolidated30-negative-20261022T222000Z-r2',
             'consolidated30-policy-fixture-20261022T221100Z-r2',
             'consolidated30-setter-fixture-20261022T221300Z-r2',
             'consolidated30-public-fixture-20261022T221300Z-r2',
             'consolidated30-parser-geometry-20261022T221300Z-r2',
             'consolidated30-residual-20261022T221800Z-r4',
             'chanset461-kernel-adapter-syntax-20261022T193600Z-r15',
             'chanset461-r15-actual-start-beacon-20261022T225800Z-r2',
             'chanset461-r15-actual-next-end-20261022T225900Z-r2',
             'chanset461-r15-review-handoff-20261022T230000Z-r1')
    for name in names:
        folder = ROOT / 'outputs/rea' / name
        for source in sorted(folder.iterdir()):
            if source.is_file() and source.suffix in EVIDENCE_EXT:
                copy(source, Path('evidence') / name / source.name)
    for name in ('prepare_chanset461_scan_advance_fix.py', 'prepare_chanset461_scan_beacon_gate.py',
                 'test_chanset461_actual_scan_end_timer.py'):
        copy(ROOT / 'tools' / name, Path('tools/integration/chanset461-r15') / name)
    for row in ROWS:
        assert hashlib.sha256((ROOT / row['source']).read_bytes()).hexdigest() == row['sha256']
        assert hashlib.sha256((REPO / row['path']).read_bytes()).hexdigest() == row['sha256']
    result = {'schema': 'openmitrastar.preservation-checkpoint/v1',
              'files': ROWS, 'hardware_accessed': False,
              'selected_combined_qualified_records': 30,
              'remaining_original_records': 14,
              'chanset461_scope': 'r15 source, actual flow fixtures and ARC unit; combined32 pending'}
    manifest.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'files': len(ROWS), 'bytes': sum(row['bytes'] for row in ROWS),
                      'all_copies_exact': True, 'manifest': str(manifest)}))


if __name__ == '__main__':
    main()
