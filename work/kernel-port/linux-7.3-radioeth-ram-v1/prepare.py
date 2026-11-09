"""Compose Ethernet MAC-init v3 plus read-only TX diagnostics; no hardware."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

DIAGNOSTIC = r'''
static ssize_t qtn_emac_txdiag(struct net_device *ndev, char *buf)
{
 struct qtn_topaz_emac *emac;
 struct qtn_topaz_emac_desc *head, *tail;
 u16 head_index, tail_index;
 u32 config;
 ssize_t result;

 if (!ndev)
  return -ENODEV;
 /* Serializes with ndo_stop/open/remove. Never block a teardown via sysfs. */
 if (!rtnl_trylock())
  return -EBUSY;
 emac = netdev_priv(ndev);
 config = qtn_emac_read(emac, QTN_EMAC_DMA_CONFIG);
 if (config & QTN_EMAC_DMA_CONFIG_SOFT_RESET) {
  result = -EBUSY;
  goto done;
 }
 head_index = READ_ONCE(emac->tx_head);
 tail_index = READ_ONCE(emac->tx_tail);
 if (!emac->tx_descs || head_index >= QTN_TOPAZ_EMAC_TX_RING_COUNT ||
     tail_index >= QTN_TOPAZ_EMAC_TX_RING_COUNT) {
  result = -ENODEV;
  goto done;
 }
 head = &emac->tx_descs[head_index];
 tail = &emac->tx_descs[tail_index];
 /* STATUS is debug-selector dependent. Expose the raw selected value and
  * selector together; do not change the selector or interpret it as pointers.
  * Address/filter/pause identity registers are intentionally absent.
  */
 result = sysfs_emit(buf,
  "schema=1\nmac_id=%u\nphy_id=%u\nactive_speed=%u\nfull_duplex=%u\n"
  "tx_head=%u\ntx_tail=%u\ntx_head_status=%08x\ntx_head_control=%08x\n"
  "tx_tail_status=%08x\ntx_tail_control=%08x\n"
  "dma_config=%08x\ndma_status=%08x\ndma_ctrl=%08x\ncur_tx=%08x\n"
  "mac_global=%08x\nmac_tx=%08x\nmac_rx=%08x\nmac_flow=%08x\n"
  "max_frame=%08x\ntx_jabber=%08x\nrx_jabber=%08x\npause_time=%08x\n"
  "tx_almost_full=%08x\ntx_threshold=%08x\nmac_interrupt=%08x\n"
  "rxp_ctrl=%08x\ntxp_ctrl=%08x\ntxp_q_full=%08x\ntxp_desc=%08x\n"
  "debug_selector=%08x\ntxp_status_raw=%08x\n",
  emac->mac_id, emac->phy_addr, READ_ONCE(emac->active_speed),
  READ_ONCE(emac->active_full_duplex), head_index, tail_index,
  qtn_desc_read(&head->status), qtn_desc_read(&head->control),
  qtn_desc_read(&tail->status), qtn_desc_read(&tail->control), config,
  qtn_emac_read(emac, QTN_EMAC_DMA_STATUS_IRQ),
  qtn_emac_read(emac, QTN_EMAC_DMA_CTRL),
  qtn_emac_read(emac, QTN_EMAC_DMA_CUR_TXDESC_PTR),
  qtn_emac_read(emac, QTN_EMAC_MAC_GLOBAL_CTRL),
  qtn_emac_read(emac, QTN_EMAC_MAC_TX_CTRL),
  qtn_emac_read(emac, QTN_EMAC_MAC_RX_CTRL),
  qtn_emac_read(emac, QTN_EMAC_MAC_FLOW_CTRL),
  qtn_emac_read(emac, QTN_EMAC_MAC_MAX_FRAME_SIZE),
  qtn_emac_read(emac, QTN_EMAC_MAC_TX_JABBER_SIZE),
  qtn_emac_read(emac, QTN_EMAC_MAC_RX_JABBER_SIZE),
  qtn_emac_read(emac, QTN_EMAC_MAC_FLOW_PAUSE_TIMEVAL),
  qtn_emac_read(emac, QTN_EMAC_MAC_TX_ALMOST_FULL),
  qtn_emac_read(emac, QTN_EMAC_MAC_TX_START_THRESHOLD),
  qtn_emac_read(emac, QTN_EMAC_MAC_INT),
  qtn_emac_read(emac, QTN_TOPAZ_EMAC_RXP_CTRL),
  qtn_emac_read(emac, QTN_TOPAZ_EMAC_TXP_CTRL),
  qtn_emac_read(emac, QTN_TOPAZ_EMAC_TXP_Q_FULL),
  qtn_emac_read(emac, QTN_TOPAZ_EMAC_TXP_DESC_PTR),
  qtn_emac_read(emac, QTN_TOPAZ_EMAC_DEBUG_BUS_SEL),
  qtn_emac_read(emac, QTN_TOPAZ_EMAC_TXP_STATUS));
done:
 rtnl_unlock();
 return result;
}
'''

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    baseline = ROOT / 'work/kernel-port/linux-7.3-ethernet-macinit-v3/candidate'
    assert sha(baseline / 'driver/qtn-topaz-emac-eth73.c') == '291fbe6d7259b12ab121c4fe2b42eeeaab9434860e6591afc40c445de2ffc425'
    shutil.copytree(baseline, a.output)
    header = a.output / 'driver/topaz-ethernet.h'
    text = header.read_text()
    text = text.replace('#define QTN_TOPAZ_EMAC_TXP_STATUS', '#define QTN_TOPAZ_EMAC_DEBUG_BUS_SEL\t0x0328\n#define QTN_TOPAZ_EMAC_TXP_STATUS')
    header.write_text(text, newline='\n')
    driver = a.output / 'driver/qtn-topaz-emac-eth73.c'
    text = driver.read_text()
    anchor = 'static ssize_t lyoko_emac_stats_show('
    assert text.count(anchor) == 1
    driver.write_text(text.replace(anchor, DIAGNOSTIC + '\n' + anchor), newline='\n')
    pair = a.output / 'driver/f352_pair.inc'
    text = pair.read_text()
    anchor = 'static DEVICE_ATTR_RO(lyoko_emac_port_stats);'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '\nstatic ssize_t lyoko_emac_txdiag_show(struct device *dev,\n struct device_attribute *attr,char *buf)\n{return qtn_emac_txdiag(to_net_dev(dev),buf);}\nstatic DEVICE_ATTR_RO(lyoko_emac_txdiag);')
    anchor = ' ret=device_create_file(&ndev->dev,&dev_attr_lyoko_emac_port_stats);if(ret)goto unregister;'
    assert text.count(anchor) == 1
    text = text.replace(anchor, anchor + '\n ret=device_create_file(&ndev->dev,&dev_attr_lyoko_emac_txdiag);if(ret){device_remove_file(&ndev->dev,&dev_attr_lyoko_emac_port_stats);goto unregister;}')
    anchor = ' emac=netdev_priv(ndev);device_remove_file(&ndev->dev,&dev_attr_lyoko_emac_port_stats);'
    assert text.count(anchor) == 1
    text = text.replace(anchor, ' emac=netdev_priv(ndev);device_remove_file(&ndev->dev,&dev_attr_lyoko_emac_txdiag);device_remove_file(&ndev->dev,&dev_attr_lyoko_emac_port_stats);')
    pair.write_text(text, newline='\n')
    records = [{'path': f.relative_to(a.output).as_posix(), 'sha256': sha(f), 'bytes': f.stat().st_size}
               for f in sorted((a.output / 'driver').rglob('*')) if f.is_file()]
    manifest = {'schema': 'openmitrastar.radioeth73-driver/v1', 'hardware_accessed': False,
                'base': 'MAC-init-v3 plus passive TX diagnostics', 'physical': 'UNRUN', 'files': records}
    (a.output / 'DRIVER_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'status': 'SOURCE_PREPARED_PHYSICAL_UNRUN', 'driver_sha256': sha(driver)}))

if __name__ == '__main__':
    main()
