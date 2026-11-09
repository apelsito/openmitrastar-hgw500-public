"""Copy selected offline source/evidence byte for byte into the private repo.

No hardware, configuration, original-source modification or binary publishing.
Run once; existing identical files are accepted, any changed file is refused.
"""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
ROWS = []
SOURCE_EXT = {'.c', '.h', '.inc', '.S', '.s', '.mk', '.json', '.patch', '.md'}
EVIDENCE_EXT = {'.c', '.h', '.json', '.md', '.py', '.stderr'}


def copy(source, relative):
    source = Path(source)
    destination = REPO / relative
    raw = source.read_bytes()
    if destination.exists():
        assert destination.read_bytes() == raw, str(destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    assert source.read_bytes() == raw and destination.read_bytes() == raw
    ROWS.append({'path': destination.relative_to(REPO).as_posix(),
                 'source': source.relative_to(ROOT).as_posix(), 'bytes': len(raw),
                 'sha256': hashlib.sha256(raw).hexdigest(), 'copy': 'EXACT_BYTES'})


def main():
    manifest = REPO / 'manifests/preservation-checkpoint-20261022-coex26-chanset-r13-r1.json'
    assert not manifest.exists(), 'already sealed'
    for name in ('coex449-source26-bss-geometry-20261022T192600Z-r3',
                 'chanset461-kernel-adapter-20261022T192700Z-r13'):
        folder = ROOT / 'outputs/rea' / name
        for source in sorted(folder.rglob('*')):
            if source.is_file() and (source.suffix in SOURCE_EXT or source.name in {'Makefile', 'Kconfig'}):
                copy(source, Path('candidates') / name / source.relative_to(folder))
    for name in ('driver5g-ops-20261022-coex26-qualification-r3',
                 'coex449-r3-independent-final-modules-20261022T220300Z-r1',
                 'coex26-handoff-20261022T191800Z-r3',
                 'chanset461-kernel-adapter-syntax-20261022T192800Z-r13',
                 'chanset461-r13-independent-kernel-fixed-20261022T224600Z-r1',
                 'chanset461-r13-actual-vdetach-fixed-20261022T224500Z-r1',
                 'chanset461-r12-actual-start-guard-20261022T224000Z-r1'):
        folder = ROOT / 'outputs/rea' / name
        for source in sorted(folder.iterdir()):
            if source.is_file() and source.suffix in EVIDENCE_EXT:
                copy(source, Path('evidence') / name / source.name)
    # Versioned tool snapshots avoid rewriting previously sealed tool copies.
    for name in ('test_chanset461_kernel_critical_review.py',
                 'test_chanset461_actual_scan_start.py',
                 'test_chanset461_actual_detach_rearm.py'):
        copy(ROOT / 'tools' / name, Path('tools/integration/chanset461-r13') / name)
    for row in ROWS:
        assert hashlib.sha256((ROOT / row['source']).read_bytes()).hexdigest() == row['sha256']
        assert hashlib.sha256((REPO / row['path']).read_bytes()).hexdigest() == row['sha256']
    result = {'schema': 'openmitrastar.preservation-checkpoint/v1',
              'files': ROWS, 'hardware_accessed': False,
              'selected_combined_qualified_records': 29,
              'coex449_scope': 'qualified separately on CoC25; combined30 pending',
              'chanset461_scope': 'r13 source and bounded fixtures only; unqualified full flow'}
    manifest.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'files': len(ROWS), 'bytes': sum(row['bytes'] for row in ROWS),
                      'all_copies_exact': True, 'manifest': str(manifest)}))


if __name__ == '__main__':
    main()
