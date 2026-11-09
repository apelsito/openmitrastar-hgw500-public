"""Regression for a missing boot-log marker and actual Ethernet identity drift."""
from pathlib import Path
import argparse
import hashlib
import json
import unittest
import f364_ethernet_identity as gate
from f336_wdt_ram_executor import Failure
from dtb_find_nodes import parse


def fixture():
    rows = {}
    for name, irq, carrier in [('eth0', 20, 0), ('eth1', 19, 1)]:
        rows.update({name+'_driver': '../../../bus/platform/drivers/qtn-topaz-emac-f352',
                     name+'_node': '../../../firmware/devicetree/base'+gate.NODE,
                     name+'_bridge': '1', name+'_carrier': str(carrier), name+'_irq': str(irq)})
    rows.update({gate.key(prop): hashlib.sha256(value).hexdigest() for prop, value in gate.DT_VALUES.items()})
    return rows


def encoded(rows):
    return ''.join(k+'='+v+'\n' for k, v in rows.items()).encode('ascii')


class Identity(unittest.TestCase):
    def test_no_boot_log_required(self):
        result = gate.verify_ethernet_response(encoded(fixture()))
        self.assertTrue(result['eth1']['carrier'])
        self.assertFalse(result['eth0']['carrier'])
        self.assertNotIn('dmesg', gate.ethernet_command())
        self.assertNotIn('mac-address', gate.ethernet_command())

    def test_properties_match_pinned_real_dt(self):
        path = Path('/workspace/OpenMitraStar-build/f363/f363-qualified-components-20260921T204529Z/f363.dtb')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), 'c1aa1111c2cb7b3cea6ebf62abba42bb078fcc7f5858026c294cb3fb421b6d6a')
        node = next(n for n in parse(path) if n['path'] == gate.NODE)
        props = dict(node['props'])
        for prop, value in gate.DT_VALUES.items():
            self.assertEqual(props[prop], value, prop)

    def test_wrong_dt_rejected(self):
        rows = fixture(); rows[gate.key('qtn,phy-addresses')] = '0'*64
        with self.assertRaises(Failure): gate.verify_ethernet_response(encoded(rows))

    def test_wrong_driver_node_or_irq_rejected(self):
        for key, value in [('eth1_driver', '/other'), ('eth1_node', '/other'), ('eth1_irq', '20')]:
            rows = fixture(); rows[key] = value
            with self.assertRaises(Failure): gate.verify_ethernet_response(encoded(rows))

    def test_missing_or_duplicate_fields_rejected(self):
        rows = fixture(); del rows['eth1_driver']
        with self.assertRaises(Failure): gate.verify_ethernet_response(encoded(rows))
        with self.assertRaises(Failure): gate.verify_ethernet_response(encoded(fixture())+b'eth0_irq=20\n')

    def test_disconnected_or_unbridged_rejected(self):
        for key in ('eth1_carrier', 'eth0_bridge'):
            rows = fixture(); rows[key] = '0'
            with self.assertRaises(Failure): gate.verify_ethernet_response(encoded(rows))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--result', type=Path, required=True); args = ap.parse_args()
    run = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Identity))
    args.result.write_text(json.dumps(dict(passed=run.wasSuccessful(), tests=run.testsRun, hardware_actions=False), indent=2)+'\n')
    raise SystemExit(0 if run.wasSuccessful() else 1)
