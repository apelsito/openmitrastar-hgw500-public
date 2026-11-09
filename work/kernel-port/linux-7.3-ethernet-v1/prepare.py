#!/usr/bin/env python3
"""Compose an isolated Linux 7.3 Ethernet candidate from sealed local inputs.
No device access. Never changes BASIC, the OEM dump or an existing output.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASIC = ROOT / 'work/kernel-port/linux-7.3-basic'
BASE = ROOT / 'work/kernel-port/f374r3-ethernet-rx-quiesce'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def replace(text, old, new):
    assert text.count(old) == 1, (old[:100], text.count(old))
    return text.replace(old, new)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists(), 'Choose an absent output directory'
    assert sha(BASE / 'qtn-topaz-emac-f352.c') == '33a3eb4a25469f39927c4b429dfb40b7afd3f54a8cf319c4c1e727bcab21b82c'
    assert sha(BASIC / 'basic73.patch') == 'd36ed090cdcb9470eb301933c066b2c7cde12de3af5c1cf3d02d9a7509088192'
    args.output.mkdir(parents=True)
    pins = []
    def read(path):
        pins.append({'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size})
        return path.read_text()
    def write(path, data):
        target = args.output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding='utf-8', newline='\n')
    source = read(BASE / 'qtn-topaz-emac-f352.c')
    source = replace(source, '#include <asm/unaligned.h>', '#include <linux/unaligned.h>\n#include <linux/irq.h>\n#include <linux/irqdomain.h>')
    source = replace(source, '\tbool irq_requested;', '\tbool irq_requested;\n\t/* Latched forever if stopped DMA cannot be observed. */\n\tbool dma_unsafe;')
    source = replace(source, '\temac->napi_polls++;', '\tif (unlikely(READ_ONCE(emac->dma_unsafe)))\n\t\treturn 0;\n\temac->napi_polls++;')
    source = replace(source, '\temac->poll_ticks++;', '\t/* Serialize full worker with stop/open without blocking RTNL cancellation. */\n\tif (!rtnl_trylock())\n\t\tgoto retry_poll;\n\tif (!netif_running(emac->ndev) || READ_ONCE(emac->dma_unsafe)) {\n\t\trtnl_unlock();\n\t\treturn;\n\t}\n\temac->poll_ticks++;')
    source = replace(source, 'rearm_poll:\n\tif (emac->irq_poll_fallback', 'rearm_poll:\n\trtnl_unlock();\nretry_poll:\n\tif (emac->irq_poll_fallback')
    # The failed trylock path must not print uninitialized trace locals.
    source = replace(source, '\tif (!rtnl_trylock())\n\t\tgoto retry_poll;', '\tif (!rtnl_trylock()) {\n\t\tif (emac->irq_poll_fallback && netif_running(emac->ndev))\n\t\t\tschedule_delayed_work(&emac->irq_poll_work, delay);\n\t\treturn;\n\t}')
    source = replace(source, 'retry_poll:\n', '')
    # Gate every destructor; timeout may never recycle hardware-owned memory.
    for func, variable in [('qtn_emac_free_rx_buffers', 'unsigned int i;'),
                           ('qtn_emac_free_tx_buffers', 'unsigned int i;'),
                           ('qtn_emac_free_rings', None)]:
        start = source.index('static void '+func+'(')
        brace = source.index('{', start)
        if variable:
            pos = source.index(variable, brace) + len(variable)
        else:
            pos = brace + 1
        source = source[:pos] + '\n\tif (READ_ONCE(emac->dma_unsafe))\n\t\treturn; /* Quarantine until a hardware reset outside this driver. */\n' + source[pos:]
    source = replace(source, '\tqtn_desc_zero(emac->tx_descs, QTN_TOPAZ_EMAC_TX_RING_COUNT);\n\tqtn_desc_zero(emac->rx_descs, QTN_TOPAZ_EMAC_RX_RING_COUNT);\n\temac->tx_head = 0;', '''\t/* A failed stop permanently bars reopening and descriptor recycling. */
\tif (READ_ONCE(emac->dma_unsafe))
\t\treturn -EIO;
\t/* Stop inherited/previous DMA BEFORE touching descriptors or buffers. */
\tret = qtn_emac_quiesce(emac);
\tif (ret) {
\t\tWRITE_ONCE(emac->dma_unsafe, true);
\t\treturn ret;
\t}
\tqtn_desc_zero(emac->tx_descs, QTN_TOPAZ_EMAC_TX_RING_COUNT);
\tqtn_desc_zero(emac->rx_descs, QTN_TOPAZ_EMAC_RX_RING_COUNT);
\temac->tx_head = 0;''')
    source = replace(source, 'err_free_irq:\n\tqtn_emac_disable_irqs(emac);', '''err_free_irq:
\t/* No worker is scheduled yet. Disable both IRQ and NAPI before final stop. */
\tqtn_emac_disable_irqs(emac);''')
    source = replace(source, 'err_disable_napi:\n\tnapi_disable(&emac->napi);\nerr_free_rx:', '''err_disable_napi:
\tnapi_disable(&emac->napi);
\t/* NAPI completion may have unmasked hardware before disable returned. */
\tif (qtn_emac_quiesce(emac))
\t\tWRITE_ONCE(emac->dma_unsafe, true);
err_free_rx:''')
    source = replace(source, '\tbool cancelled = false;\n\n\tWRITE_ONCE', '\tbool cancelled = false;\n\tint ret;\n\n\tWRITE_ONCE')
    source = replace(source, '''\tqtn_emac_disable_irqs(emac);
\tqtn_emac_quiesce(emac);
\tif (emac->irq_requested) {
\t\tsynchronize_irq(emac->irq);
\t\tfree_irq(emac->irq, ndev);
\t\temac->irq_requested = false;
\t}
\tnapi_disable(&emac->napi);
\tqtn_emac_free_tx_buffers(emac);''', '''\tqtn_emac_disable_irqs(emac);
\tif (emac->irq_requested)
\t\tdisable_irq(emac->irq);
\tnapi_disable(&emac->napi);
\t/* Final stop follows NAPI shutdown; no late completion can unmask IRQ. */
\tret = qtn_emac_quiesce(emac);
\tif (ret) {
\t\tWRITE_ONCE(emac->dma_unsafe, true);
\t\tnetdev_err(ndev, "DMA stop timeout; buffers pinned, reopen refused\\n");
\t}
\tif (emac->irq_requested) {
\t\tfree_irq(emac->irq, ndev);
\t\temac->irq_requested = false;
\t}
\tqtn_emac_free_tx_buffers(emac);''')
    source = replace(source, '.compatible = "openmitrastar,f352-dual-emac"', '.compatible = "openmitrastar,eth73-v1-dual-emac"')
    source = replace(source, '.name = "qtn-topaz-emac-f352"', '.name = "qtn-topaz-emac-eth73"')
    write('driver/qtn-topaz-emac-eth73.c', source)
    pair = read(BASE / 'f352_pair.inc')
    pair = replace(pair, 'netif_napi_add(ndev,&emac->napi,qtn_emac_poll,QTN_TOPAZ_EMAC_NAPI_WEIGHT)', 'netif_napi_add_weight(ndev,&emac->napi,qtn_emac_poll,QTN_TOPAZ_EMAC_NAPI_WEIGHT)')
    pair = replace(pair, 'ether_addr_copy(ndev->dev_addr,pair->addresses[index])', 'eth_hw_addr_set(ndev,pair->addresses[index])')
    pair = replace(pair, 'struct f352_lifecycle ops;const void *address;u32 ids[2],phys[2],reset;', 'struct f352_lifecycle ops;u8 address[ETH_ALEN];struct irq_data *irqdata;u32 ids[2],phys[2],reset;')
    pair = replace(pair, 'address=of_get_mac_address(dev->of_node);\n if(IS_ERR_OR_NULL(address)||!is_valid_ether_addr(address))return -EINVAL;', 'ret=of_get_mac_address(dev->of_node,address);\n if(ret)return ret;\n if(!is_valid_ether_addr(address))return -EINVAL;')
    pair = replace(pair, 'ret=platform_get_irq_byname(pdev,names[i]);if(ret<0)return ret;if(ret!=irqs[i])return -EINVAL;', '''ret=platform_get_irq_byname(pdev,names[i]);if(ret<0)return ret;
  irqdata=irq_get_irq_data(ret);
  if(!irqdata||irqdata->hwirq!=irqs[i]||!irqdata->domain||
     !of_device_is_compatible(irq_domain_get_of_node(irqdata->domain),"snps,arc700-intc"))return -EINVAL;''')
    pair = replace(pair, 'static int qtn_emac_remove(', 'static void qtn_emac_remove(')
    pair = replace(pair, 'if(!ndev)return 0;', 'if(!ndev)return;')
    pair = replace(pair, 'platform_set_drvdata(pdev,NULL);return 0;', 'platform_set_drvdata(pdev,NULL);')
    pair = replace(pair, 'qtn,f352-dual-direct', 'qtn,eth73-dual-direct')
    write('driver/f352_pair.inc', pair)
    write('driver/f352_contract.h', read(BASE / 'f352_contract.h'))
    write('driver/topaz-ethernet.h', read(ROOT / 'work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h'))
    write('driver/Makefile', 'obj-m += qtn-topaz-emac-eth73.o\n')
    gate = read(BASIC / 'overlay/arch/arc/kernel/intc-compact.c')
    gate = replace(gate, 'hwirq != TOPAZ_BASIC_UART_PARENT', '(hwirq != TOPAZ_BASIC_UART_PARENT &&\n        (!IS_ENABLED(CONFIG_QTN_TOPAZ_ETH73) || (hwirq != 19 && hwirq != 20)))')
    gate = replace(gate, 'BIT(TOPAZ_BASIC_UART_PARENT - TOPAZ_BASIC_GATE_BASE)', 'BIT(hwirq - TOPAZ_BASIC_GATE_BASE)') if gate.count('BIT(TOPAZ_BASIC_UART_PARENT - TOPAZ_BASIC_GATE_BASE)') == 1 else gate.replace('BIT(TOPAZ_BASIC_UART_PARENT - TOPAZ_BASIC_GATE_BASE)', 'BIT(hwirq - TOPAZ_BASIC_GATE_BASE)')
    gate = replace(gate, '/* BASIC Topaz board only: UART aggregator uses LHOST gate 24 - 5.\n * No PCIe, GPIO, network, watchdog or other direct IRQ route is touched.\n */', '/* UART BASIC retains only hwirq24. ETH73 additionally gates direct hwirq19/20.\n * All other LHOST bits are preserved by the serialized read/modify/write. */')
    write('overlay/arch/arc/kernel/intc-compact.c', gate)
    dt = read(BASIC / 'overlay/arch/arc/boot/dts/topaz_mitrastar_basic73.dts')
    dt = replace(dt, 'Linux 7.3 BASIC UART', 'Linux 7.3 Ethernet v1')
    dt = replace(dt, '\t\tranges;', '\t\tranges;\n\t\t/* Topaz DMA bus DDR 0..128MiB maps CPU physical 0x80000000. */\n\t\tdma-ranges = <0x00000000 0x80000000 0x08000000>;')
    node = '''
\t\tethernet@e8000000 {
\t\t\tcompatible = "openmitrastar,eth73-v1-dual-emac";
\t\t\treg = <0xe8000000 0x400>, <0xed000000 0x400>;
\t\t\treg-names = "emac1", "emac0";
\t\t\tinterrupt-parent = <&core_intc>;
\t\t\tinterrupts = <20>, <19>;
\t\t\tinterrupt-names = "emac1", "emac0";
\t\t\tqtn,eth73-dual-direct;
\t\t\tqtn,phy-addresses = <3 1>;
\t\t\tqtn,mac-ids = <1 0>;
\t\t\t/* No per-unit identity in shared source: probe refuses until
\t\t\t * an exact authorized runtime plan supplies the real owner MAC. */
\t\t\tstatus = "disabled";
\t\t};
'''
    dt = replace(dt, '\n\t\tuart0: serial@f0000000', node+'\n\t\tuart0: serial@f0000000')
    write('overlay/arch/arc/boot/dts/topaz_mitrastar_eth73.dts', dt)
    config = read(BASIC / 'basic73.config.template')
    config = config.replace('CONFIG_LOCALVERSION="-openmitrastar-basic73"', 'CONFIG_LOCALVERSION="-openmitrastar-eth73-v1"')
    config = config.replace('CONFIG_BUILTIN_DTB_NAME="topaz_mitrastar_basic73"', 'CONFIG_BUILTIN_DTB_NAME="topaz_mitrastar_eth73"')
    for key in ['NET', 'INET', 'NETDEVICES', 'ETHERNET', 'SYSFS', 'MODULES']:
        config = config.replace('# CONFIG_'+key+' is not set', 'CONFIG_'+key+'=y')
        if 'CONFIG_'+key+'=y' not in config:
            config += '\nCONFIG_'+key+'=y\n'
    # The RX restart worker is qualified only for a UP non-preemptible kernel.
    config = config.replace('CONFIG_PREEMPT_VOLUNTARY_BUILD=y', '# CONFIG_PREEMPT_VOLUNTARY_BUILD is not set')
    config = config.replace('CONFIG_PREEMPT_VOLUNTARY=y', '# CONFIG_PREEMPT_VOLUNTARY is not set')
    config += '\nCONFIG_PREEMPT_NONE=y\nCONFIG_PREEMPT_NONE_BUILD=y\nCONFIG_QTN_TOPAZ_ETH73=y\nCONFIG_MODULE_UNLOAD=y\n# CONFIG_WLAN is not set\n# CONFIG_IPV6 is not set\n'
    write('eth73.config.template', config)
    (args.output / 'manifest.json').write_text(json.dumps({
        'schema': 'openmitrastar.eth73-source/v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'classification': 'OFFLINE_DIAGNOSTIC_NO_GO_HARDWARE', 'hardware_accessed': False,
        'base_kernel_commit': 'c03c1a14507dfaf8b856c2608f9ac216021fc222',
        'basic_patch_sha256': sha(BASIC/'basic73.patch'), 'inputs': pins,
        'outputs': [{'path': p.relative_to(args.output).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size}
                    for p in sorted(args.output.rglob('*')) if p.is_file()],
        'limits': ['DT Ethernet disabled and no unit MAC supplied.',
                   'DMA timeout latches quarantine: memory retained even on netdev removal.',
                   'No reset recovery on timeout; reopening refused until external hardware reset.',
                   'No hardware, traffic, reset, runtime or release acceptance.']}, indent=2)+'\n')
    print(args.output)

if __name__ == '__main__':
    main()
