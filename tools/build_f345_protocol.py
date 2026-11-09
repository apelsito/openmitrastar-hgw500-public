"""Offline serial-command encoding only; no Topaz MMIO or hardware executor."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT/'work/kernel-port/modules/f345_spi_nor_protocol'


def linux(path):
    path = path.resolve()
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'outputs/kernel-port'/('f345-protocol-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    (out/'source').mkdir()
    for name in ('f345_protocol.h', 'f345_protocol.c', 'test_f345_protocol.c'):
        shutil.copyfile(SOURCE/name, out/'source'/name)
    tc = linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-')
    script = f'''set -eu
out={shlex.quote(linux(out))}
tc={shlex.quote(tc)}
flags='-std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes'
gcc $flags -O2 "$out/source/f345_protocol.c" "$out/source/test_f345_protocol.c" -o "$out/host-tests"
"$out/host-tests" > "$out/tests.stdout"
gcc $flags -fanalyzer -c "$out/source/f345_protocol.c" -o "$out/analyzer.o"
for lane in a b; do
 mkdir "$out/$lane"
 SOURCE_DATE_EPOCH=1790006400 "${{tc}}gcc" $flags -Os -g0 -mno-atomic -mno-sdata -fno-stack-protector -fstack-usage -c "$out/source/f345_protocol.c" -o "$out/$lane/f345_protocol.o"
 "${{tc}}ar" rcsD "$out/$lane/libf345protocol.a" "$out/$lane/f345_protocol.o"
 "${{tc}}nm" -u "$out/$lane/f345_protocol.o" > "$out/$lane/imports.txt"
 "${{tc}}objdump" -d "$out/$lane/f345_protocol.o" > "$out/$lane/disassembly.txt"
 "${{tc}}readelf" -h "$out/$lane/f345_protocol.o" > "$out/$lane/elf.txt"
done
cmp "$out/a/libf345protocol.a" "$out/b/libf345protocol.a"
'''
    (out/'build.sh').write_bytes(script.encode())
    process = subprocess.run(['wsl.exe', '-d', 'podman-mem9-tidb', '-u', 'root', '-e', 'sh', linux(out/'build.sh')],
                             capture_output=True, timeout=90)
    (out/'build.stdout').write_bytes(process.stdout)
    (out/'build.stderr').write_bytes(process.stderr)
    artifact = out/'a/libf345protocol.a'
    tests = (out/'tests.stdout').read_text(encoding='utf-8') if (out/'tests.stdout').exists() else ''
    result = {
        'schema': 'openmitrastar.f345-serial-protocol/v1',
        'status': 'PASS_OFFLINE_SERIAL_PROTOCOL_ONLY' if process.returncode == 0 else 'FAIL_OFFLINE_BUILD',
        'hardware_actions': False, 'mmio_backend_implemented': False,
        'actual_flash_part_verified': False, 'persistent_writes_enabled': False,
        'tests': tests,
        'sources': {str(p.relative_to(out)): sha(p) for p in (out/'source').iterdir()},
        'artifact': {'path': str(artifact), 'bytes': artifact.stat().st_size, 'sha256': sha(artifact)} if artifact.exists() else None,
        'reproducible': artifact.exists() and (out/'b/libf345protocol.a').exists() and sha(artifact) == sha(out/'b/libf345protocol.a'),
        'limitation': 'Encoded SPI bytes require a separately qualified controller transport, ownership, readiness polls, readback and exact chip identity.',
    }
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'result': str(out/'result.json'), **result, 'build_error_tail': process.stderr.decode(errors='replace')[-2200:]}, indent=2))
    return int(process.returncode != 0)


if __name__ == '__main__':
    raise SystemExit(main())
