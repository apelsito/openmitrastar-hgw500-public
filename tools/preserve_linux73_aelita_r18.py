"""Preserve the private R18 source delivery and exact build evidence; no hardware."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
PACKAGE = ROOT / 'outputs/rea/linux73-full44-candidate-20261023T002000Z-r18'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    rows = []
    def preserve(source, destination):
        src = ROOT / source
        dst = REPO / destination
        if not src.is_file():
            raise ValueError('Missing source: ' + str(src))
        if dst.exists() and dst.read_bytes() != src.read_bytes():
            raise ValueError('Existing immutable file differs: ' + str(dst))
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copyfile(src, dst)
        rows.append({'path': destination, 'source': source,
                     'bytes': src.stat().st_size, 'sha256': digest(src),
                     'copy': 'EXACT_BYTES'})
    for src in sorted(PACKAGE.rglob('*')):
        if not src.is_file():
            continue
        if src.suffix.lower() in ('.o', '.ko', '.elf', '.pem', '.key', '.p12', '.pyc'):
            raise ValueError('Source package includes excluded artifact: ' + str(src))
        preserve(src.relative_to(ROOT).as_posix(),
                 'src/linux-7.3-r18/' + src.relative_to(PACKAGE).as_posix())
    for name in ('linux73_build_current.py', 'linux73_build_current_ipv6.py'):
        preserve('tools/' + name, 'tools/' + name)
    for name in ('fix_hgw5g_linux73_native_provider_api.py', 'fix_hgw5g_linux73_gpio_api.py'):
        preserve('tools/' + name, 'tools/integration/linux73-r18/' + name)
    for name in ('LINUX73_AELITA_CURRENT_BUILD.md', 'LINUX73_AELITA_CURRENT_IPV6_BUILD.md'):
        preserve('docs/' + name, 'docs/' + name)
    for folder in ('linux73-current-r16-plancheck-20261022T213200Z-r1',
                   'linux73-current-r16-ipv6-plancheck-20261022T213500Z-r1',
                   'linux73-full44-72c-compile-receipt-20261023T002500Z-r18'):
        for src in sorted((ROOT / 'outputs/rea' / folder).rglob('*')):
            if src.is_file() and src.suffix in ('.json', '.log'):
                preserve(src.relative_to(ROOT).as_posix(),
                         'evidence/' + folder + '/' + src.name)
    manifest = REPO / 'manifests/preservation-checkpoint-20261022-linux73-native-r18.json'
    value = {'schema': 'openmitrastar.preservation-checkpoint/v1', 'files': rows,
             'repository_visibility': 'private', 'target_kernel': 'Linux7.3',
             'hardware_accessed': False, 'source_package': 'src/linux-7.3-r18',
             'limits': 'Exact source preservation. Compile evidence, full linkage, pair/ABI and physical gates are separate.'}
    data = (json.dumps(value, indent=2) + '\n').encode()
    if manifest.exists() and manifest.read_bytes() != data:
        raise ValueError('Existing checkpoint differs')
    manifest.write_bytes(data)
    print(json.dumps({'status': 'PASS_EXACT_PRIVATE_R18_SOURCE_COPY', 'files': len(rows),
                      'manifest_sha256': digest(manifest), 'hardware_accessed': False}))

if __name__ == '__main__':
    main()
