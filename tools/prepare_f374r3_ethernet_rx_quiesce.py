"""Generate F374r3, preserving F352/F374/F374r2 and prior evidence.

Same RX ownership fix; an active NAPI mask of zero restores supported DMA IRQs.
Only supported on the pinned single-core PREEMPT_NONE runtime/build contract.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import prepare_f374r2_ethernet_rx_quiesce as previous

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT/'work/kernel-port/f374r3-ethernet-rx-quiesce'


def render(original):
    rendered = previous.render(original)
    rendered = previous.parent.replace(rendered,
        '\tirq_mask = qtn_emac_read(emac, QTN_EMAC_DMA_INT_ENABLE);\n'
        '\tmac_rx_ctrl = qtn_emac_read(emac, QTN_EMAC_MAC_RX_CTRL);',
        '\t/* Called only by the running-netdev worker on the pinned single-core\n'
        '\t * PREEMPT_NONE kernel. SMP/preemptible NAPI-tail interleavings are\n'
        '\t * outside this candidate\'s qualified configuration. A zero snapshot\n'
        '\t * is NAPI masking, so completion must restore the supported mask.\n'
        '\t */\n'
        '\tirq_mask = qtn_emac_read(emac, QTN_EMAC_DMA_INT_ENABLE);\n'
        '\tif (!irq_mask)\n'
        '\t\tirq_mask = QTN_EMAC_DMA_IRQ_TX_DONE |\n'
        '\t\t\t   QTN_EMAC_DMA_IRQ_RX_DONE | QTN_EMAC_DMA_IRQ_MAC;\n'
        '\tmac_rx_ctrl = qtn_emac_read(emac, QTN_EMAC_MAC_RX_CTRL);')
    return rendered


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEST)
    args = parser.parse_args()
    assert not args.output.exists(), 'output exists; preserve prior candidate'
    base = previous.parent.BASE
    for name, digest in previous.parent.PINS.items():
        assert previous.sha(base/name) == digest, 'F352 drift '+name
    original = (base/'qtn-topaz-emac-f352.c').read_text()
    rendered = render(original)
    old_stop = original[original.index('static int qtn_emac_stop('):original.index('static const struct net_device_ops')]
    new_stop = rendered[rendered.index('static int qtn_emac_stop('):rendered.index('static const struct net_device_ops')]
    assert old_stop == new_stop
    args.output.mkdir(parents=True, exist_ok=False)
    for name in ('f352_contract.h', 'f352_pair.inc', 'Makefile'):
        shutil.copyfile(base/name, args.output/name)
    source = args.output/'qtn-topaz-emac-f352.c'
    source.write_text(rendered, newline='\n')
    manifest = {'schema': 'openmitrastar.f374r3-ethernet-rx-quiesce/v1',
                'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'NO_GO_INSTALL', 'hardware_accessed': False,
                'firmware_created': False, 'baseline_pins': previous.parent.PINS,
                'source_pins': {p.name: previous.sha(p) for p in args.output.iterdir() if p.is_file()},
                'generators': {str(p): previous.sha(p) for p in (Path(__file__).resolve(), Path(previous.__file__).resolve(), Path(previous.parent.__file__).resolve())},
                'change': 'Require current RX DMA state stopped before descriptor rearm; restore exact nonzero IRQ masks and supported TX/RX/MAC mask for NAPI-masked zero snapshots.',
                'revision': 'r2 retained; zero IRQ snapshot no longer disables subsequent interrupt delivery.',
                'required_configuration': {'CONFIG_SMP': False, 'CONFIG_PREEMPT_NONE': True,
                                           'caller': 'running netdev irq_poll_work; no external/offline helper invocation'},
                'limits': ['Inherited ndo_stop/remove DMA lifetime gap remains unresolved.',
                           'SMP/preemptible NAPI completion tail remains outside qualification.',
                           'No reset added; not packaged, installed or physically accepted.']}
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    for name, digest in previous.parent.PINS.items():
        assert previous.sha(base/name) == digest, 'F352 changed during generation '+name
    print(json.dumps({'status': manifest['status'], 'output': str(args.output), 'source_sha256': previous.sha(source)}))


if __name__ == '__main__':
    main()
