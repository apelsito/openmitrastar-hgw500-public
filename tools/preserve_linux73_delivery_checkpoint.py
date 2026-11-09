"""Copy explicit source/evidence into the private driver repository byte for byte."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
ALLOWED = {'.py', '.c', '.h', '.S', '.s', '.json', '.md', '.html', '.bin', '.log', '.patch', '.gz'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--copy', action='append', nargs=2, metavar=('SOURCE', 'DESTINATION'), required=True)
    args = parser.parse_args()
    manifest = REPO / 'manifests' / ('preservation-checkpoint-' + args.checkpoint + '.json')
    if manifest.exists():
        raise ValueError('Checkpoint already exists')
    rows = []
    for source, destination in args.copy:
        srcroot, dstroot = ROOT / source, REPO / destination
        if not srcroot.exists() or '..' in Path(source).parts or '..' in Path(destination).parts:
            raise ValueError('Missing or unsafe input')
        files = sorted(srcroot.rglob('*')) if srcroot.is_dir() else [srcroot]
        for src in files:
            if not src.is_file():
                continue
            if src.suffix in ('.o', '.ko', '.elf', '.pem', '.key', '.pyc', '.p12'):
                raise ValueError('Excluded binary or private asset: ' + str(src))
            if src.suffix == '.bin' and src.name != 'comments.raw.bin':
                raise ValueError('Only exact comment byte streams may use .bin')
            dst = dstroot / src.relative_to(srcroot) if srcroot.is_dir() else dstroot
            if dst.exists() and dst.read_bytes() != src.read_bytes():
                raise ValueError('Existing copy differs: ' + str(dst))
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                shutil.copyfile(src, dst)
            rows.append({'path': dst.relative_to(REPO).as_posix(),
                         'source': src.relative_to(ROOT).as_posix(),
                         'bytes': src.stat().st_size,
                         'sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
                         'copy': 'EXACT_BYTES'})
    manifest.write_text(json.dumps({'schema': 'openmitrastar.preservation-checkpoint/v1',
        'files': rows, 'repository_visibility': 'private', 'hardware_accessed': False}, indent=2) + '\n')
    print(json.dumps({'status': 'PASS_EXACT_CHECKPOINT_COPY', 'files': len(rows), 'manifest': str(manifest)}))

if __name__ == '__main__':
    main()
