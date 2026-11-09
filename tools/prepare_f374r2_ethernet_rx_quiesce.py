"""Generate F374r2 from exact F352, preserving the initial F374 candidate.

The timeout counter is appended to the private struct so all existing field
offsets remain unchanged. Same single RX-quiesce ownership change as F374.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import prepare_f374_ethernet_rx_quiesce as parent

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'work/kernel-port/f374r2-ethernet-rx-quiesce'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def render(original):
    rendered = parent.render(original)
    rendered = parent.replace(rendered, '\tu32 poll_rx_quiesce_timeouts;\n', '')
    rendered = parent.replace(rendered, '\tu32 rx_restart_reason_stagnant;\n};',
                              '\tu32 rx_restart_reason_stagnant;\n'
                              '\tu32 poll_rx_quiesce_timeouts;\n};')
    return rendered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEST)
    args = parser.parse_args()
    assert not args.output.exists(), 'output exists; preserve prior candidate'
    for name, digest in parent.PINS.items():
        assert sha(parent.BASE/name) == digest, 'F352 drift '+name
    original = (parent.BASE/'qtn-topaz-emac-f352.c').read_text()
    rendered = render(original)
    old_stop = original[original.index('static int qtn_emac_stop('):original.index('static const struct net_device_ops')]
    new_stop = rendered[rendered.index('static int qtn_emac_stop('):rendered.index('static const struct net_device_ops')]
    assert old_stop == new_stop
    args.output.mkdir(parents=True, exist_ok=False)
    for name in ('f352_contract.h', 'f352_pair.inc', 'Makefile'):
        shutil.copyfile(parent.BASE/name, args.output/name)
    source = args.output/'qtn-topaz-emac-f352.c'
    source.write_text(rendered, newline='\n')
    manifest = {'schema': 'openmitrastar.f374r2-ethernet-rx-quiesce/v1',
                'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'NO_GO_INSTALL', 'hardware_accessed': False,
                'firmware_created': False, 'baseline_pins': parent.PINS,
                'source_pins': {p.name: sha(p) for p in args.output.iterdir() if p.is_file()},
                'generators': {str(p): sha(p) for p in (Path(__file__).resolve(), Path(parent.__file__).resolve())},
                'change': 'Require current RX DMA state stopped before descriptor rearm; exact control restoration and separate timeout counter appended to private struct.',
                'revision': 'Original F374 retained; counter location moved to preserve all existing private field offsets.',
                'limits': ['Inherited ndo_stop/remove DMA lifetime gap remains unresolved.',
                           'No reset added; same F352 module/DT identity for complete comparison.',
                           'Not packaged, installed or physically accepted.']}
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    for name, digest in parent.PINS.items():
        assert sha(parent.BASE/name) == digest, 'F352 changed during generation '+name
    print(json.dumps({'status': manifest['status'], 'output': str(args.output), 'source_sha256': sha(source)}))


if __name__ == '__main__':
    main()
