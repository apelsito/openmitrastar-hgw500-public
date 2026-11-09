"""Rebuild the existing passive F320 control snapshot for exact F340, offline.

No device contact, module load, flash command, deliberate CPU stop, or firmware
image creation occurs. The module source and its two reads remain unchanged.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import shlex
import shutil
import subprocess

import build_f320_spi_control_probe as existing

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT/'outputs/preflight/f340-qualified-20260921T134752Z/handoff.json'
EXPECTED_HANDOFF = '63214c4adaed55f42a04e51b6499c1d3797a1b1b034557a3605f44fb35d8e626'
MODULE_CONTEXT = Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f341-closure-20260921T134402Z/manifest.json'
EXPECTED_CONTEXT = '14b8ff7b809937f08e07b6213c7c2b6be5b3a5d653f78205575935c4ee980315'
NAME = 'qtn-topaz-spi-control-probe'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if sha(HANDOFF) != EXPECTED_HANDOFF:
        raise ValueError('F340 handoff changed')
    handoff = json.loads(HANDOFF.read_text(encoding='utf-8'))
    image = Path(handoff['image']['path'])
    if sha(image) != handoff['image']['sha256']:
        raise ValueError('F340 image changed')
    prefix = str(image)[:-len('.webformat.bin')]
    kernel = Path(prefix+'.vmlinux')
    config = Path(prefix+'.config')
    if sha(MODULE_CONTEXT) != EXPECTED_CONTEXT:
        raise ValueError('Prepared module context proof changed')
    context = json.loads(MODULE_CONTEXT.read_text(encoding='utf-8'))
    if context['status'] != 'PASS_F341_COHERENT_CLOSURE' or context['kernel_config_sha256'] != sha(config) or context['kernel_vmlinux_sha256'] != sha(kernel):
        raise ValueError('Prepared context is not the exact F340 kernel')
    symvers = Path(handoff['kernel_module_symvers'])
    if sha(symvers) != handoff['kernel_module_symvers_sha256']:
        raise ValueError('F340 exported-symbol table changed')
    source = existing.SOURCE
    existing.check_source((source/(NAME+'.c')).read_text(encoding='utf-8'))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'outputs/kernel-port'/('f347-passive-spi-control-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    (out/'source').mkdir()
    for name in (NAME+'.c', 'Makefile', 'test_f320_shim.h', 'test_f320_control_probe.c'):
        shutil.copyfile(source/name, out/'source'/name)
    shutil.copyfile(symvers, out/'f340.Module.symvers')
    q = shlex.quote
    tc = existing.wsl(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')
    script = f'''set -eu
out={q(existing.wsl(out))}
src={q(handoff['kernel_source'])}
kout={q(context['isolated_module_context'])}
tc={q(tc)}
test "$(sha256sum "$kout/.config" | cut -d ' ' -f1)" = {sha(config)}
test "$(sha256sum "$out/f340.Module.symvers" | cut -d ' ' -f1)" = {handoff['kernel_module_symvers_sha256']}
extra="KBUILD_EXTRA_SYMBOLS=$out/f340.Module.symvers"
if test -f "$kout/Module.symvers"; then
 cmp "$kout/Module.symvers" "$out/f340.Module.symvers"
 extra=''
fi
gcc -std=gnu11 -O2 -Wall -Wextra -Werror -fanalyzer "$out/source/test_f320_control_probe.c" -o "$out/host-test"
"$out/host-test" > "$out/tests.stdout"
for lane in a b; do
 mkdir "$out/$lane"
 cp "$out/source/{NAME}.c" "$out/source/Makefile" "$out/$lane/"
 make -C "$src" O="$kout" M="$out/$lane" ARCH=arc CROSS_COMPILE="$tc" $extra modules > "$out/$lane/build.log" 2>&1
done
cmp "$out/a/{NAME}.ko" "$out/b/{NAME}.ko"
"${{tc}}objdump" -dr "$out/a/{NAME}.ko" > "$out/disassembly.txt"
"${{tc}}readelf" -h "$out/a/{NAME}.ko" > "$out/elf.txt"
"${{tc}}nm" -u "$out/a/{NAME}.ko" > "$out/imports.txt"
"${{tc}}nm" {q(existing.wsl(kernel))} > "$out/kernel-symbols.txt"
test "$(sha256sum "$kout/.config" | cut -d ' ' -f1)" = {sha(config)}
test "$(sha256sum "$out/f340.Module.symvers" | cut -d ' ' -f1)" = {handoff['kernel_module_symvers_sha256']}
'''
    (out/'build.sh').write_bytes(script.encode())
    p = subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',existing.wsl(out/'build.sh')],
                       capture_output=True, timeout=180)
    (out/'build.stdout').write_bytes(p.stdout)
    (out/'build.stderr').write_bytes(p.stderr)
    errors = []
    if p.returncode:
        errors.append('build failed')
    else:
        existing.check_read_helpers((out/'disassembly.txt').read_text(encoding='ascii'))
        symbols = (out/'kernel-symbols.txt').read_text(encoding='ascii')
        for row in (out/'imports.txt').read_text(encoding='ascii').splitlines():
            name = row.split()[-1]
            if not re.search(r'\b__ksymtab_'+re.escape(name)+r'$',symbols,re.M):
                errors.append('unexported kernel symbol: '+name)
        if 'ARC700, v4 ABI' not in (out/'elf.txt').read_text():
            errors.append('unexpected ARC ABI')
    artifact = out/'a'/(NAME+'.ko')
    report = {
        'schema':'openmitrastar.f347-passive-spi-control/v1',
        'status':'PASS_OFFLINE_REBUILD_DEVICE_EXECUTION_UNRUN' if not errors else 'FAIL_OFFLINE_REBUILD',
        'errors':errors, 'hardware_actions':False, 'firmware_created':False,
        'source_changed_from_f320':False, 'deliberate_cpu_fault':False,
        'mmio_scope':{'sysctl_map_reads':1,'spi_control_reads':1,'writes':0,'flash_command_apertures':0},
        'tests':(out/'tests.stdout').read_text() if (out/'tests.stdout').exists() else '',
        'artifact':{'path':str(artifact),'bytes':artifact.stat().st_size,'sha256':sha(artifact)} if artifact.exists() else None,
        'sources':{str(x):sha(x) for x in [HANDOFF,MODULE_CONTEXT,kernel,config,symvers,Path(__file__),Path(existing.__file__),*(out/'source').iterdir()]},
        'execution_status':'UNRUN; no inference of SPI bus decoding or transaction ownership',
    }
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'result':str(out/'result.json'),'status':report['status'],'artifact':report['artifact'],'errors':errors,
                      'build_error_tail':p.stderr.decode(errors='replace')[-1000:]},indent=2))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
