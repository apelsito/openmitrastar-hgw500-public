"""Add omitted OEM per-port MAC limits to reset-v2; no hardware access."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE_SHA = '9f49c8a9c6478a18793062d87c051132ea6812a557ea24ae006b50f21e93fd33'

REGISTERS = {
    'TX_JABBER_SIZE': 0x110, 'RX_JABBER_SIZE': 0x114,
    'TABLE1': 0x150, 'TABLE2': 0x154, 'TABLE3': 0x158, 'TABLE4': 0x15c,
    'FLOW_SA_HIGH': 0x168, 'FLOW_SA_MED': 0x16c, 'FLOW_SA_LOW': 0x170,
    'FLOW_PAUSE_TIMEVAL': 0x180, 'TX_ALMOST_FULL': 0x1c0,
    'TX_START_THRESHOLD': 0x1c4,
}

HELPER = '''static void qtn_emac_oem_mac_limits(struct qtn_topaz_emac *emac)
{
\tconst u8 *address = emac->ndev->dev_addr;

\t/* OEM emac_lib_init_mac(): initialize the current EMAC's local FIFO,
\t * pause and filter settings after stopped DMA has been observed.
\t * Never inherit these values from Bootbase or the previous kernel.
\t * This does not write PHY, SYSCTL, TQE, HBM or the neighboring EMAC.
\t */
\tqtn_emac_write(emac, QTN_EMAC_MAC_TX_JABBER_SIZE, 0xca0);
\tqtn_emac_write(emac, QTN_EMAC_MAC_RX_JABBER_SIZE, 0xca0);
\tqtn_emac_write(emac, QTN_EMAC_MAC_TABLE1, 0);
\tqtn_emac_write(emac, QTN_EMAC_MAC_TABLE2, 0);
\tqtn_emac_write(emac, QTN_EMAC_MAC_TABLE3, 0);
\tqtn_emac_write(emac, QTN_EMAC_MAC_TABLE4, 0);
\tqtn_emac_write(emac, QTN_EMAC_MAC_FLOW_SA_HIGH,
\t\t       get_unaligned_le16(address));
\tqtn_emac_write(emac, QTN_EMAC_MAC_FLOW_SA_MED,
\t\t       get_unaligned_le16(address + 2));
\tqtn_emac_write(emac, QTN_EMAC_MAC_FLOW_SA_LOW,
\t\t       get_unaligned_le16(address + 4));
\tqtn_emac_write(emac, QTN_EMAC_MAC_FLOW_PAUSE_TIMEVAL, 100);
\tqtn_emac_write(emac, QTN_EMAC_MAC_TX_ALMOST_FULL, 0x1f8);
\tqtn_emac_write(emac, QTN_EMAC_MAC_TX_START_THRESHOLD, 1518);
}

'''

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    baseline = ROOT / 'work/kernel-port/linux-7.3-ethernet-reset-v2/candidate'
    assert sha(baseline / 'driver/qtn-topaz-emac-eth73.c') == BASE_SHA
    shutil.copytree(baseline, args.output)
    header = args.output / 'driver/topaz-ethernet.h'
    definitions = header.read_text()
    anchor = '#define QTN_EMAC_MAC_ADDR_CTRL'
    assert definitions.count(anchor) == 1
    position = definitions.index(anchor)
    additions = ''.join(f'#define QTN_EMAC_MAC_{name}\t\t0x{offset:04x}\n'
                        for name, offset in REGISTERS.items())
    header.write_text(definitions[:position] + additions + definitions[position:], newline='\n')
    driver = args.output / 'driver/qtn-topaz-emac-eth73.c'
    text = driver.read_text()
    # Keep the new register definitions inside this versioned module package.
    include = '#include <linux/soc/qtn/topaz-ethernet.h>'
    assert text.count(include) == 1
    text = text.replace(include, '#include "topaz-ethernet.h"')
    anchor = 'static int qtn_emac_speed_bits('
    assert text.count(anchor) == 1
    text = text.replace(anchor, HELPER + anchor)
    anchor = '\tqtn_emac_program_address(emac);\n'
    # This helper is only called from hw_start; do not alter set-address paths.
    start = text.index('static int qtn_emac_hw_start(')
    end = text.index('static int qtn_emac_restart_rx_dma(', start)
    part = text[start:end]
    assert part.count(anchor) == 1
    part = part.replace(anchor, anchor + '\tqtn_emac_oem_mac_limits(emac);\n')
    text = text[:start] + part + text[end:]
    driver.write_text(text, newline='\n')
    manifest = {
        'schema': 'openmitrastar.eth73-oem-mac-init/v3',
        'base_driver_sha256': BASE_SHA, 'hardware_accessed': False,
        'change': 'Initialize twelve omitted OEM local MAC registers before enabling TX/RX.',
        'hypothesis': 'Inherited FIFO or pause configuration may explain eth1 WaitEOT TX stall.',
        'root_cause_confirmed': False, 'physical': 'UNRUN',
        'retained': 'Reset-v2 stopped-state validation and failed-reset DMA quarantine.',
        'files': [{'path': f.relative_to(args.output).as_posix(),
                   'sha256': sha(f), 'bytes': f.stat().st_size}
                  for f in sorted((args.output / 'driver').rglob('*')) if f.is_file()],
    }
    (args.output / 'MACINIT_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'status': 'SOURCE_PREPARED_PHYSICAL_UNRUN', 'driver_sha256': sha(driver)}))

if __name__ == '__main__':
    main()
