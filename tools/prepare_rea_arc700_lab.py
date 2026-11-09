"""Prepare a project-local REA 6.7.0 ARC700 static-analysis development lane.

Runs in REA-Linux. Never patches the installed REA runtime, Codex configuration,
original module bytes, or hardware. This is a bounded local adaptation, not
upstream-supported ARC700 functionality or an emulation oracle.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

ROOT = Path('/workspace/user-home/Desktop/MitraStar')
BASE = Path('/opt/rea/npm/lib/node_modules/rea-agents')
GHIDRA = Path('/opt/rea/ghidra_12.1.4_PUBLIC')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    runtime = out / 'rea-agents'
    runtime.mkdir()
    for name in ('dist', 'bridge', 'scripts'):
        shutil.copytree(BASE / name, runtime / name)
    for name in ('package.json', 'LICENSE', 'README.md'):
        shutil.copyfile(BASE / name, runtime / name)
    (runtime / 'node_modules').symlink_to(BASE / 'node_modules', target_is_directory=True)

    patches = []
    # Patch each compiled copy of the header decoder, including the CLI bundle.
    # Recognition stays a genuine ARC identity; no ELF header is relabelled.
    for path in (runtime / 'dist').rglob('*.js'):
        original = path.read_text()
        text = original
        text = re.sub(r'(case 164:\s*(?://[^\n]*\n\s*)?return "hexagon";)',
                      'case 93: return "arc700";\n' + r'\1', text)
        # Provider admission and provider-neutral output-schema CPU lists.
        text = re.sub(r'("hexagon")(\s*,?\s*\])', r'\1, "arc700"\2', text)
        if 'architecture: elfArchitecture(machine) ?? null' in text:
            needle = 'const machine = readU16(18);'
            if needle not in text:
                raise RuntimeError('header decoder shape changed: ' + str(path))
            gate = '''
    if (machine === 93 && (elfClass !== 32 || !littleEndian ||
        ![1, 2].includes(readU16(16)) ||
        ![0x3, 0x403].includes(readU32(36))))
        return err("ARC700 local lane requires ELF32 LE ET_REL/ET_EXEC flags 0x3/0x403");
'''
            text = text.replace(needle, needle + gate)
        if text != original:
            before = sha(path)
            path.write_text(text)
            patches.append({'path': str(path.relative_to(runtime)),
                            'upstream_sha256': before, 'local_sha256': sha(path)})
    if not any('peMachine-' in x['path'] for x in patches):
        raise RuntimeError('bundled header decoder was not patched')
    if not any('binary-' in x['path'] for x in patches):
        raise RuntimeError('bundled provider admission was not patched')

    # Ghidra resolves its application root from physical jar paths. A view
    # with symlinked Framework jars silently selects the original root and
    # misses our processor. Use an independent working installation.
    view = out / 'ghidra_12.1.4_PUBLIC'
    shutil.copytree(GHIDRA, view)
    processors = view / 'Ghidra/Processors'
    module = processors / 'ARCompact'
    module.mkdir()
    source = ROOT / 'work/ghidra-arcompact-build'
    shutil.copytree(source / 'data', module / 'data')
    shutil.copyfile(source / 'Module.manifest', module / 'Module.manifest')
    shutil.copyfile(source / 'LICENSE', module / 'LICENSE.txt')
    # The historical emulator hook has no role in static decompilation. Omit
    # that optional unavailable Java class and explicitly forbid emulation.
    pspec = module / 'data/languages/ARCompact.pspec'
    pspec.write_text(re.sub(r'\s*<properties>.*?</properties>', '',
                           pspec.read_text(), flags=re.S))
    compiled = module / 'data/languages/ARCompact.sla'
    with (out / 'sleigh.stdout').open('wb') as stdout, (out / 'sleigh.stderr').open('wb') as stderr:
        result = subprocess.run([str(view / 'support/sleigh'),
                                 str(module / 'data/languages/ARCompact.slaspec'),
                                 str(compiled)], stdout=stdout, stderr=stderr,
                                timeout=180)
    if result.returncode or not compiled.is_file():
        raise RuntimeError('Sleigh compilation failed; inspect ' + str(out))

    manifest = {
        'schema': 'openmitrastar.rea-arc700-lab/v1',
        'status': 'PREPARED_REQUIRES_REAL_BINARY_VALIDATION',
        'upstream_version': json.loads((BASE / 'package.json').read_text())['version'],
        'runtime': str(runtime), 'ghidra': str(view), 'patches': patches,
        'language_id': 'ARCompact:LE:32:default', 'compiler_spec_id': 'default',
        'source_language_pins': {str(p.relative_to(source)): sha(p)
                                 for p in sorted((source / 'data').rglob('*')) if p.is_file()},
        'compiled_language_sha256': sha(compiled),
        'installed_rea_modified': False, 'codex_config_modified': False,
        'original_artifacts_modified': False, 'hardware_accessed': False,
        'limitations': ['Project-local REA adaptation; not upstream ARC support.',
                       'Static analysis only; ARC instruction and ABI semantics require independent verification.',
                       'ARCompact ELF relocation completeness remains unknown.',
                       'Emulator hook omitted; no target execution or RF evidence.'],
    }
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'prepared': str(out), 'patch_count': len(patches),
                      'sleigh_sha256': sha(compiled)}))


if __name__ == '__main__':
    prepare(Path(sys.argv[1]).resolve())
