"""Seal actual source-object evidence at the kernel-provider MODPOST boundary."""
import argparse
import datetime
import hashlib
import json
import re
import shutil
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--kernel-context', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    text = args.log.read_text()
    assert 'MODPOST Module.symvers' in text
    assert not re.search(r'\berror:', text)
    units = []
    for group in ('source', 'providers'):
        for path in sorted((args.build_root / group).rglob('*.o')):
            rel = path.relative_to(args.build_root)
            src = args.candidate / rel.with_suffix('.c')
            assert src.is_file(), str(src)
            assert sha(src) == sha(args.build_root / rel.with_suffix('.c'))
            units.append({'path': str(rel), 'bytes': path.stat().st_size,
                          'sha256': sha(path), 'source_sha256': sha(src)})
    assert len(units) == 72, len(units)
    shutil.copyfile(args.log, args.output / 'modpost-boundary.log')
    result = {
        'status': 'PASS_72_REAL_LINUX73_C_UNITS_KERNEL_EXPORT_REBUILD_PENDING',
        'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'candidate': str(args.candidate),
        'candidate_result_sha256': sha(args.candidate / 'result.json'),
        'kernel_config_sha256': sha(args.kernel_context / '.config'),
        'kernel_symvers_sha256': sha(args.kernel_context / 'Module.symvers'),
        'C_units': len(units), 'units': units,
        'log_sha256': sha(args.log),
        'visible_modpost_unresolved': re.findall(r"symbol '([^']+)' undefined", text),
        'modpost_suppression_reported': 'suppressed' in text,
        'kernel_full_build_pass': False, 'module_link_pass': False,
        'hardware_accessed': False, 'firmware_eligible': False,
    }
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'C_units': len(units),
                      'result_sha256': sha(args.output / 'result.json')}, indent=2))


if __name__ == '__main__':
    main()
