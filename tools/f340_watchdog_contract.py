"""F340 reuses the F336 inactive-driver/DT contracts with a new identity."""
from pathlib import Path
import copy
import f336_wdt_ram_contract as base

ROOT, DEVICE, F321, F321_BASE = base.ROOT, base.DEVICE, base.F321, base.F321_BASE
F329, F329_SOURCE = base.F329, base.F329_SOURCE
F336 = DEVICE/'analysis/f336-wdt-ram-20260921T123734Z'
MARKER = b'F340_WATCHDOG_BASELINE\0'
STAGING, CRC_SCRATCH, LOAD, ENTRY, DDR_END = base.STAGING, base.CRC_SCRATCH, base.LOAD, base.ENTRY, base.DDR_END
sha, require, node_map, cells, reservations, serialize = base.sha, base.require, base.node_map, base.cells, base.reservations, base.serialize


def make_dt(original, target):
    intermediate = target.parent/'f336-reference-dtb-for-identity-replacement.bin'
    contract = base.make_dt(original, intermediate)
    require(intermediate.read_bytes() == (F336/'a/f336.dtb').read_bytes(), 'F336 reference DT drift')
    nodes = copy.deepcopy(base.parse_dtb(intermediate))
    for node in nodes:
        if node['path'] == '/':
            node['props'] = [(k, v) for k, v in node['props'] if k != 'openmitrastar,f336-wdt-ram']
            node['props'].append(('openmitrastar,f340-watchdog-baseline', MARKER))
        elif node['path'] == '/f336-watchdog-clock':
            node['name'] = 'f340-watchdog-clock'
            node['path'] = '/f340-watchdog-clock'
    target.write_bytes(serialize(nodes, intermediate.read_bytes()))
    require(b'F336_WDT_RAM_ONLY' not in target.read_bytes() and b'openmitrastar,f336-wdt-ram' not in target.read_bytes(), 'old RAM identity survived')
    expected = node_map(intermediate)
    actual = node_map(target)
    expected['/'].pop('openmitrastar,f336-wdt-ram')
    expected['/']['openmitrastar,f340-watchdog-baseline'] = MARKER
    expected['/f340-watchdog-clock'] = expected.pop('/f336-watchdog-clock')
    require(actual == expected, 'F340 DT changed beyond identity')
    contract.update(candidate_sha256=sha(target), identity='F340_WATCHDOG_BASELINE',
                    f336_reference_sha256=sha(intermediate), driver_registers_inactive=True,
                    automatic_watchdog_open=False)
    return contract


def driver_observation_overlay(source):
    reference = base.driver_observation_overlay(source)
    require(reference == (F336/'dw_wdt.c').read_bytes(), 'F336 driver observation overlay drift')
    return reference.replace(b'F336', b'F340').replace(b'f336', b'f340')
