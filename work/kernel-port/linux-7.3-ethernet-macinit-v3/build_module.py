"""Build MAC-init v3 twice in a fresh copy of the sealed radio73 context."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['candidate', 'source', 'context', 'toolchain', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    assert sha(a.candidate / 'driver/qtn-topaz-emac-eth73.c') == '291fbe6d7259b12ab121c4fe2b42eeeaab9434860e6591afc40c445de2ffc425'
    manifest = json.loads((a.candidate / 'MACINIT_MANIFEST.json').read_text())
    for row in manifest['files']:
        f = a.candidate / row['path']
        assert sha(f) == row['sha256'] and f.stat().st_size == row['bytes'], row['path']
    assert sha(a.context / 'vmlinux') == '25c726d1d5d9a0ed617985dc974452233ced07c132687acafad167bf816bacd3'
    assert sha(a.context / '.config') == 'cdbd2ddd1f4dfe018de86673d678dd891282cf0fb5edae0e359bbfdaad62de74'
    tc = str(a.toolchain / 'bin/arc-snps-linux-uclibc-')
    assert sha(Path(tc + 'gcc')) == '3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
    a.output.mkdir(parents=True)
    context = a.output / 'context'
    subprocess.run(['cp', '-a', '--reflink=auto', str(a.context), str(context)], check=True)
    env = os.environ.copy()
    env.update(SOURCE_DATE_EPOCH='1792365298', KBUILD_BUILD_TIMESTAMP='@1792365298',
               KBUILD_BUILD_USER='openmitrastar', KBUILD_BUILD_HOST='radio73', KBUILD_BUILD_VERSION='1')
    exports = {l.split()[1] for l in (context / 'Module.symvers').read_text().splitlines()}
    lanes = []
    for lane in ['a', 'b']:
        module = a.output / lane
        shutil.copytree(a.candidate / 'driver', module)
        command = ['make', '-C', str(a.source), 'O=' + str(context), 'ARCH=arc',
                   'CROSS_COMPILE=' + tc, 'M=' + str(module),
                   'KCFLAGS=-ffile-prefix-map=' + str(module) + '=/eth73-module', '-j6', 'modules']
        print('RUN module-' + lane, flush=True)
        with (a.output / ('build-' + lane + '.log')).open('xb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=300)
        ko = module / 'qtn-topaz-emac-eth73.ko'
        asm = subprocess.check_output([tc + 'objdump', '-d', str(ko)], text=True)
        assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )', asm)
        imports = [l.split()[-1] for l in subprocess.check_output([tc + 'nm', '-u', str(ko)], text=True).splitlines()]
        assert not set(imports) - exports
        lanes.append({'lane': lane, 'sha256': sha(ko), 'bytes': ko.stat().st_size,
                      'imports': len(imports), 'forbidden_instructions': 0})
    assert lanes[0]['sha256'] == lanes[1]['sha256']
    assert sha(a.context / 'vmlinux') == sha(context / 'vmlinux')
    result = {'schema': 'openmitrastar.eth73-oem-mac-module/v3', 'status': 'PASS_PAIRED_MODULE_RADIO73_CONTEXT',
              'hardware_accessed': False, 'physical': 'UNRUN', 'lanes': lanes,
              'kernel_sha256': sha(context / 'vmlinux'), 'config_sha256': sha(context / '.config'),
              'driver_sha256': sha(a.candidate / 'driver/qtn-topaz-emac-eth73.c'),
              'limits': ['Modules compile against the radio73 kernel; integrated RAM image and physical TX acceptance remain unrun.']}
    (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
