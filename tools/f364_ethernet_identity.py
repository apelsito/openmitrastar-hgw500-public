"""Read the bound F352 devices and their DT properties, independent of boot logs."""
import hashlib
import struct
from f336_wdt_ram_executor import require

NODE = '/soc/ethernet@e8000000'
DT_VALUES = {
    'compatible': b'openmitrastar,f352-dual-emac\0',
    'status': b'okay\0',
    'qtn,f352-dual-direct': b'',
    'qtn,mac-ids': struct.pack('>2I', 1, 0),
    'qtn,phy-addresses': struct.pack('>2I', 3, 1),
    'reg': struct.pack('>4I', 0xe8000000, 0x400, 0xed000000, 0x400),
    'reg-names': b'emac1\0emac0\0',
    'interrupts': struct.pack('>2I', 20, 19),
    'interrupt-names': b'emac1\0emac0\0',
}


def key(name):
    return 'dt_' + name.replace(',', '_').replace('-', '_')


def ethernet_command():
    lines = ["set -e", 'for n in eth0 eth1; do',
             'printf "%s_driver=" "$n"; readlink /sys/class/net/$n/device/driver',
             'printf "%s_node=" "$n"; readlink /sys/class/net/$n/device/of_node',
             'printf "%s_bridge=" "$n"; if [ -e /sys/class/net/br0/brif/$n ]; then echo 1; else echo 0; fi',
             'printf "%s_carrier=" "$n"; cat /sys/class/net/$n/carrier',
             'printf "%s_irq=" "$n"; sed -n "s/^irq=//p" /sys/class/net/$n/lyoko_emac_port_stats',
             'done']
    for prop in DT_VALUES:
        lines.append("printf '" + key(prop) + "='; sha256sum /sys/class/net/eth0/device/of_node/" + prop + " | awk '{print $1}'")
    return '\n'.join(lines)


def verify_ethernet_response(data):
    pairs = [line.split('=', 1) for line in data.decode('ascii').splitlines()]
    require(all(len(pair) == 2 for pair in pairs) and
            len({pair[0] for pair in pairs}) == len(pairs), 'ethernet_response')
    rows = dict(pairs)
    expected = {n + '_' + f for n in ('eth0', 'eth1')
                for f in ('driver', 'node', 'bridge', 'carrier', 'irq')}
    expected.update(key(prop) for prop in DT_VALUES)
    require(set(rows) == expected, 'ethernet_response_fields')
    for prop, value in DT_VALUES.items():
        require(rows[key(prop)] == hashlib.sha256(value).hexdigest(), 'ethernet_dt_property_' + prop)
    result = {}
    for name, mac, phy, irq in [('eth0', 1, 3, 20), ('eth1', 0, 1, 19)]:
        require(rows[name + '_driver'].endswith('/qtn-topaz-emac-f352'), 'ethernet_driver')
        require(rows[name + '_node'].endswith(NODE), 'ethernet_device_tree_node')
        require(rows[name + '_bridge'] == '1' and rows[name + '_carrier'] in ('0', '1'), 'ethernet_bridge_carrier')
        require(rows[name + '_irq'] == str(irq), 'ethernet_port_irq')
        result[name] = dict(mac=mac, phy=phy, irq=irq, bridge='br0',
                            carrier=rows[name + '_carrier'] == '1', driver='qtn-topaz-emac-f352',
                            mapping_source='bound-device-tree-and-live-irq')
    require(any(port['carrier'] for port in result.values()), 'no_ethernet_carrier')
    return result
