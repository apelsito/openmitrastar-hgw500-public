"""Generate F374 RX-quiesce candidate from immutable exact F352, offline only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'work/kernel-port/modules/f352_dual_emac'
DEST = ROOT/'work/kernel-port/f374-ethernet-rx-quiesce'
PINS = {
    'qtn-topaz-emac-f352.c': '011e42eb8fda62686b9b55dd210f1104540c5c3ec65f20d7f4035812e55e64f2',
    'f352_contract.h': '86ce6864caa11d06c127c36fdb8e9e5999c23cf61a7a07ede705b0f51d47b2a2',
    'f352_pair.inc': '1a02218b41e6769f0a3ce92e2e3705fa50a947f5337a79fa9737413ddbf2f18e',
    'Makefile': '101e08948c4117fd8c77150c955ee91d8a7944d7ac956398b9d0f6ab6f4b5a1c',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(text, old, new):
    assert text.count(old) == 1, 'anchor cardinality '+old[:80]
    return text.replace(old, new, 1)


def render(text):
    text = replace(text, '\tu32 poll_rx_dma_restarts;\n',
                   '\tu32 poll_rx_dma_restarts;\n\tu32 poll_rx_quiesce_timeouts;\n')
    text = replace(text, '"rx_restart_reason_stagnant=%u\\nrx_restart_throttled=%u\\n"',
                   '"rx_restart_reason_stagnant=%u\\nrx_restart_throttled=%u\\n"\n'
                   '\t\t"rx_quiesce_timeouts=%u\\n"')
    text = replace(text, '\t\tREAD_ONCE(emac->poll_rx_restart_throttled),\n',
                   '\t\tREAD_ONCE(emac->poll_rx_restart_throttled),\n'
                   '\t\tREAD_ONCE(emac->poll_rx_quiesce_timeouts),\n')
    start = text.index('static void qtn_emac_restart_rx_dma(')
    end = text.index('/* Temporary hardware bring-up fallback.', start)
    text = text[:start] + '''static int qtn_emac_restart_rx_dma(struct qtn_topaz_emac *emac, u32 dma_ctrl)
{
	u32 irq_mask;
	u32 mac_rx_ctrl;
	u32 rxp_ctrl;
	u32 value;
	u16 i;
	int ret;

	irq_mask = qtn_emac_read(emac, QTN_EMAC_DMA_INT_ENABLE);
	mac_rx_ctrl = qtn_emac_read(emac, QTN_EMAC_MAC_RX_CTRL);
	rxp_ctrl = qtn_emac_read(emac, QTN_TOPAZ_EMAC_RXP_CTRL);
	dma_ctrl = qtn_emac_read(emac, QTN_EMAC_DMA_CTRL);
	qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, 0);
	napi_disable(&emac->napi);
	/* A poll completing during napi_disable may have unmasked DMA IRQs. */
	qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, 0);

	qtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL, 0);
	qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL,
			mac_rx_ctrl & ~QTN_EMAC_MAC_RX_ENABLE);
	qtn_emac_write(emac, QTN_EMAC_DMA_CTRL,
			dma_ctrl & ~QTN_EMAC_DMA_CTRL_START_RX);
	/* RX_STOPPED is latched status, not proof of current DMA ownership. */
	ret = readl_poll_timeout(emac->regs + QTN_EMAC_DMA_STATUS_IRQ, value,
				 !(value & QTN_EMAC_DMA_RX_STATE_MASK),
				 10, QTN_TOPAZ_EMAC_RX_RESTART_QUIESCE_US);
	if (ret) {
		/* Preserve every descriptor/buffer and the consumer index. Restore
		 * the exact producer state from DMA outward before IRQ delivery.
		 */
		qtn_emac_write(emac, QTN_EMAC_DMA_CTRL, dma_ctrl);
		qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL, mac_rx_ctrl);
		qtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL, rxp_ctrl);
		napi_enable(&emac->napi);
		qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, irq_mask);
		return ret;
	}

	for (i = 0; i < QTN_TOPAZ_EMAC_RX_RING_COUNT; i++)
		qtn_emac_rearm_rx(emac, i);
	emac->rx_head = 0;

	qtn_emac_write(emac, QTN_EMAC_DMA_RX_BASE_ADDR,
			lower_32_bits(emac->rx_descs_dma));
	qtn_emac_write(emac, QTN_EMAC_DMA_STATUS_IRQ,
			QTN_EMAC_DMA_IRQ_RX_DONE |
			QTN_EMAC_DMA_IRQ_NO_RX_DESC |
			QTN_EMAC_DMA_IRQ_RX_STOPPED |
			QTN_EMAC_DMA_IRQ_RX_MISSED);
	dma_wmb();
	qtn_emac_write(emac, QTN_EMAC_DMA_CTRL,
			dma_ctrl | QTN_EMAC_DMA_CTRL_START_RX);
	qtn_emac_write(emac, QTN_EMAC_MAC_RX_CTRL,
			mac_rx_ctrl | QTN_EMAC_MAC_RX_ENABLE);
	qtn_emac_write(emac, QTN_TOPAZ_EMAC_RXP_CTRL,
			QTN_TOPAZ_EMAC_RXP_ENABLE |
			QTN_TOPAZ_EMAC_RXP_SYNC_RX_DMA);
	qtn_emac_write(emac, QTN_EMAC_DMA_RX_POLL_DEMAND, 0);
	napi_enable(&emac->napi);
	qtn_emac_write(emac, QTN_EMAC_DMA_INT_ENABLE, irq_mask);
	return 0;
}

''' + text[end:]
    text = replace(text, '\tu32 mac_pending;\n\tbool progress;',
                   '\tu32 mac_pending;\n\tint rx_restart_ret;\n\tbool progress;')
    start = text.index('\t\t\tif (dma_status & QTN_EMAC_DMA_IRQ_RX_STOPPED)\n')
    end = text.index('\n\t\t}\n\t}\n\nrearm_poll:', start)
    block = text[start:end]
    block = replace(block, '\t\t\temac->poll_rx_dma_restarts++;\n'
                    '\t\t\tqtn_emac_restart_rx_dma(emac, dma_ctrl);\n',
                    '\t\t\temac->poll_rx_dma_restarts++;\n')
    block = replace(block, '\t\t\temac->poll_last_rx_restart_jiffies = jiffies;\n', '')
    text = text[:start] + '''			/* Cool down failed attempts too; they are not successful restarts. */
			rx_restart_ret = qtn_emac_restart_rx_dma(emac, dma_ctrl);
			emac->poll_last_rx_restart_jiffies = jiffies;
			if (rx_restart_ret) {
				emac->poll_rx_quiesce_timeouts++;
				goto rearm_poll;
			}
''' + block + text[end:]
    text = replace(text, '\temac->poll_rx_dma_restarts = 0;\n',
                   '\temac->poll_rx_dma_restarts = 0;\n\temac->poll_rx_quiesce_timeouts = 0;\n')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEST)
    args = parser.parse_args()
    assert not args.output.exists(), 'output exists; preserve prior candidate'
    for name, digest in PINS.items():
        assert sha(BASE/name) == digest, 'F352 source drift '+name
    original = (BASE/'qtn-topaz-emac-f352.c').read_text()
    rendered = render(original)
    # The inherited stop/remove paths are intentionally outside this delta.
    old_stop = original[original.index('static int qtn_emac_stop('):original.index('static const struct net_device_ops')]
    new_stop = rendered[rendered.index('static int qtn_emac_stop('):rendered.index('static const struct net_device_ops')]
    assert old_stop == new_stop, 'unexpected stop change'
    args.output.mkdir(parents=True, exist_ok=False)
    for name in ('f352_contract.h', 'f352_pair.inc', 'Makefile'):
        shutil.copyfile(BASE/name, args.output/name)
    source = args.output/'qtn-topaz-emac-f352.c'
    source.write_text(rendered, newline='\n')
    manifest = {'schema': 'openmitrastar.f374-ethernet-rx-quiesce/v1',
                'generated_at_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'NO_GO_INSTALL', 'hardware_accessed': False,
                'firmware_created': False, 'baseline_pins': PINS,
                'source_pins': {p.name: sha(p) for p in args.output.iterdir() if p.is_file()},
                'generator': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)},
                'change': 'Never rearm RX descriptors or reset rx_head unless current RX DMA state is stopped; restore original controls after timeout and count it separately.',
                'limits': ['Inherited ndo_stop/remove DMA lifetime gap remains unresolved.',
                           'No reset operation added; same F352 name and DT/ABI retained for comparison.',
                           'Offline candidate requires fixtures and complete build; not installed or packaged.']}
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    for name, digest in PINS.items():
        assert sha(BASE/name) == digest, 'F352 changed during generation '+name
    print(json.dumps({'status': manifest['status'], 'output': str(args.output), 'source_sha256': sha(source)}))


if __name__ == '__main__':
    main()
