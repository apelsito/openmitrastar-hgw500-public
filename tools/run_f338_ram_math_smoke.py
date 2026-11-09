"""Execute the bounded F338 math-only selftest on pinned F321, from RAM.

No UAPI, radio, UART, firmware or network configuration changes. This is not
a DFS hardware acceptance test. Each binary has its own alarm and CPU limit.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import f325_execution_contract as contract
from probe_hgw_existing_tftp_path import ssh

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / '.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis'
CASES = [
    ('control', PRIVATE/'f338-control-20260921T125724Z/f338-control-a',
     '5aeb5c1e352a1b7863853a42524bccafb825503511c04505c61ee7cd9a52994e', 9136, '',
     b'F338_CONTROL_PASS alarm_seconds=3 cpu_hard_seconds=2 hardware=0\n'),
    ('math', PRIVATE/'f338-service-20260921T132141Z/a/om-radar-engine-f338',
     '737cbdfeb429caba42929374c4a22eab549791c6af42fb3149c5ad64c048c85b', 75212, ' --selftest',
     b'F338_SELFTEST_BEGIN alarm_seconds=10 cpu_hard_seconds=5 hardware=0\n'
     b'F338_SELFTEST_PASS checks=398 classifier_vectors=55 linux_syscalls=1 hardware=0 uapi_opened=0\n'),
]


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    if sys.argv[1:] != ['--execute']:
        raise SystemExit('Explicit --execute required for the RAM-only selftest')
    for name, path, digest, size, _, _ in CASES:
        data = path.read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise SystemExit('Local immutable input mismatch: '+name)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'outputs/handoff-live'/('f338-ram-math-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    (out/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    remote = '/tmp/om-f338-math-'+stamp
    report = dict(schema='openmitrastar.f338-ram-math/v1', started_at_utc=now(),
                  status='RUNNING', tests=[], uart=False, flash=False,
                  radio_mutation=False, uapi_opened=False, output=str(out))
    version = "grep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION="+contract.F321['version']+"' /etc/openmitrastar/release"
    created = False
    try:
        p = ssh(version+' && cat /proc/sys/kernel/random/boot_id')
        if p.returncode or p.stderr.strip():
            raise ValueError('Pinned F321 identity not confirmed')
        boot_id = p.stdout.decode('ascii').strip()
        report['boot_id_before'] = boot_id
        p = ssh('umask 077; mkdir '+remote)
        if p.returncode or p.stderr.strip():
            raise ValueError('Unique RAM directory creation failed')
        created = True
        for name, path, digest, size, args, expected in CASES:
            target = remote+'/'+name
            p = ssh('cat > '+target+' && chmod 700 '+target, data=path.read_bytes())
            if p.returncode or p.stderr.strip():
                raise ValueError('RAM upload failed: '+name)
            p = ssh(version+" && test \"$(cat /proc/sys/kernel/random/boot_id)\" = '"+boot_id+
                    "' && sha256sum "+target+" | grep -q '^"+digest+" ' && "+target+args, timeout=18)
            (out/(name+'.stdout')).write_bytes(p.stdout)
            (out/(name+'.stderr')).write_bytes(p.stderr)
            passed = p.returncode == 0 and not p.stderr.strip() and p.stdout == expected
            report['tests'].append(dict(name=name, sha256=digest, bytes=size,
                returncode=p.returncode, stdout=p.stdout.decode(errors='replace'),
                stderr_bytes=len(p.stderr), passed=passed))
            if not passed:
                raise ValueError('Bounded Linux execution failed: '+name)
        p = ssh(version+' && cat /proc/sys/kernel/random/boot_id')
        report['same_f321_boot'] = p.returncode == 0 and not p.stderr.strip() and p.stdout.decode().strip() == boot_id
        if not report['same_f321_boot']:
            raise ValueError('F321 postcheck failed')
        report['status'] = 'PASS_F338_MATH_ON_REAL_ARC_LINUX_NO_HARDWARE'
    except Exception as exc:
        report['status'] = 'FAIL_F338_RAM_MATH'
        report['error'] = str(exc)
    finally:
        if created:
            try:
                # Exact freshly-created task directory; no glob or computed root.
                p = ssh('rm -rf '+remote+'; test ! -e '+remote)
                report['ram_artifacts_removed'] = p.returncode == 0 and not p.stderr.strip()
            except Exception:
                report['ram_artifacts_removed'] = False
            if not report['ram_artifacts_removed']:
                report['status'] = 'FAIL_F338_RAM_CLEANUP'
        report['finished_at_utc'] = now()
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
