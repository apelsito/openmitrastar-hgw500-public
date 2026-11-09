"""Offline-testable RAM-to-writer boundary; no native/hardware adapters or CLI.

This module cannot open UART, start a server, alter firewall state or reboot.
A separately reviewed physical executor must supply bounded callbacks under its
live lease and authorized network scope. It must not treat these unit tests as
qualification of those adapters. The old backend remains unchanged: its
`uart-ymodem` label is a constant of the preloaded-RAM branch, NOT evidence of
the actual bulk transport. Ethernet evidence is validated independently here.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from pathlib import Path
import re

from f323_execution_contract import F323, F321, ERASE_BYTES, SLOT_BYTES


RAM_SCHEMA = 'openmitrastar.f323-ethernet-ram-gate/v1'
WRITER_SCHEMA = 'openmitrastar.f323-ethernet-writer/v1'
BACKEND_SHA256 = '87ca467cd52d50b917d976ba1a8884a0892afdc677a872f601651acea1b4489b'
CRCS = {F323['sha256']: '81cec636', F321['sha256']: 'bd1135df'}
EVIDENCE_FILES = {'bootbase-flash-uart.log', 'backend.log', 'ethernet-ram-result.json',
                  'ethernet-server-result.json'}


def exact_pair(direction: str) -> tuple[dict, dict]:
    if direction == 'promote':
        return F323, F321
    if direction == 'rollback':
        return F321, F323
    raise ValueError('Ethernet handoff supports exact F323/F321 only; no automatic F314')


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def exact_server(address: str) -> str:
    value = ipaddress.IPv4Address(address)
    peer_net = ipaddress.IPv4Network('192.168.1.0/24')
    require(isinstance(address, str) and value.is_private and not (
        value.is_unspecified or value.is_loopback or value.is_link_local or value.is_multicast
    ) and value in peer_net and value not in (peer_net.network_address, peer_net.broadcast_address)
        and str(value) != '192.168.1.90', 'unscoped Ethernet server')
    return str(value)


def validate_ram_result(ram: dict, *, direction: str, server_ipv4: str) -> dict:
    image, _ = exact_pair(direction)
    server_ipv4 = exact_server(server_ipv4)
    require(isinstance(ram, dict) and ram.get('schema') == RAM_SCHEMA
        and ram.get('status') == 'PASS_ETHERNET_RAM_GATE', 'RAM gate did not pass')
    require(ram.get('candidate_sha256') == image['sha256']
        and type(ram.get('candidate_bytes')) is int and ram['candidate_bytes'] == image['bytes']
        and ram.get('candidate_crc32') == CRCS[image['sha256']]
        and ram.get('address') == '0x83000000', 'RAM gate differs from exact image')
    require(ram.get('server_closed') is True and type(ram.get('flash_writes')) is int
        and ram['flash_writes'] == 0, 'RAM gate cleanup or write scope not proven')
    server = ram.get('server_result')
    require(isinstance(server, dict), 'missing server evidence')
    require(server.get('schema') == 'openmitrastar.f323-scoped-tftp/v1'
        and server.get('status') == 'PASS_TFTP_SINGLE_TRANSFER'
        and server.get('transfer_started') is True and server.get('transfer_complete') is True
        and server.get('sockets_closed') is True and server.get('flash') is False
        and server.get('boot_verified') is False, 'server transfer/cleanup not proven')
    require(server.get('bind') == server_ipv4 and server.get('allow_client') == '192.168.1.90'
        and type(server.get('port')) is int and server['port'] == 69
        and server.get('allow_file') == image['base'] + '.webformat.bin', 'server scope mismatch')
    file = server.get('file', {})
    counts = server.get('counts', {})
    require(file.get('sha256') == image['sha256'] and type(file.get('bytes')) is int
        and file['bytes'] == image['bytes'], 'served image mismatch')
    require(type(counts.get('payload_bytes_acked')) is int and counts['payload_bytes_acked'] == image['bytes']
        and type(counts.get('blocks_acked')) is int and counts['blocks_acked'] == image['bytes'] // 512 + 1,
        'complete server ACK evidence missing')
    return {'transport': 'ethernet-tftp', 'candidate_sha256': image['sha256'],
        'bytes': image['bytes'], 'ram_crc32_observed': CRCS[image['sha256']],
        'server_ipv4': server_ipv4, 'server_closed': True}


def read_bounded(path: Path, maximum: int) -> bytes:
    require(not path.is_symlink() and path.is_file(), 'evidence is not a regular non-symlink file')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    require(len(data) <= maximum, 'evidence exceeds bounded reader')
    return data


def verify_writer_result(directory: Path, *, direction: str, server_ipv4: str,
                         expected_ram_result: dict | None = None) -> dict:
    """Check new Ethernet evidence without changing or fabricating old UART logs."""
    image, current = exact_pair(direction)
    directory = Path(directory).resolve(strict=True)
    result = json.loads(read_bounded(directory / 'result.json', 65536))
    require(result.get('schema') == WRITER_SCHEMA and result.get('status') == 'PASS'
        and result.get('candidate_sha256') == image['sha256'], 'writer outcome is not exact PASS')
    write = result.get('physical_write', {})
    require(write == {'offset': 0x7e0000, 'erase_size': ERASE_BYTES,
        'candidate_size': image['bytes'], 'slot_size': SLOT_BYTES, 'partition': 'mtd4/linux_live'},
        'writer physical scope differs')
    require(all(type(write[key]) is int for key in ('offset', 'erase_size', 'candidate_size', 'slot_size')),
        'writer physical dimensions must be integers')
    flash = result.get('flash', {})
    require(result.get('backend_sha256') == BACKEND_SHA256
        and flash == {'control_transport': 'uart-bootbase',
            'network_transfer_performed': False, 'skip_reboot': True, 'skip_network_transfer': True}
        and all(type(flash[key]) is bool for key in ('network_transfer_performed', 'skip_reboot', 'skip_network_transfer')),
        'writer backend or preloaded-only mode differs')
    readback = result.get('readback', {})
    require(readback.get('full_slot_crc32') == image['full_slot_crc32']
        and readback.get('candidate_prefix_compare') == 'PASS'
        and result.get('protected_partitions', {}).get('status') == 'PASS', 'writer readback incomplete')
    evidence = result.get('evidence', [])
    require(isinstance(evidence, list) and len(evidence) == len(EVIDENCE_FILES), 'wrong evidence set')
    bound = {}
    for item in evidence:
        name = item.get('path')
        require(name in EVIDENCE_FILES and name not in bound, 'unexpected or duplicate evidence path')
        path = directory / name
        require(path.resolve().parent == directory, 'evidence escaped the attempt directory')
        data = read_bounded(path, 4 * 1024 * 1024 if name.endswith('.log') else 65536)
        require(hashlib.sha256(data).hexdigest() == item.get('sha256'), 'evidence hash mismatch')
        bound[name] = data
    require(set(bound) == EVIDENCE_FILES, 'missing Ethernet evidence')
    ram = json.loads(bound['ethernet-ram-result.json'])
    if expected_ram_result is not None:
        require(ram == expected_ram_result, 'writer evidence did not retain this RAM result')
    ram_proof = validate_ram_result(ram, direction=direction, server_ipv4=server_ipv4)
    require(json.loads(bound['ethernet-server-result.json']) == ram['server_result'],
        'server and RAM evidence are from different results')

    trace = bound['bootbase-flash-uart.log'].decode('utf-8', errors='strict')
    backend = bound['backend.log'].decode('utf-8', errors='strict')
    require(re.findall(r'Total of ([0-9]+) bytes? were the same', trace) == [str(image['bytes'])],
        'full candidate comparison count missing or ambiguous')
    mutations = re.findall(r'spi_flash\s+(erase|write)\s+([^\r\n]+)', trace)
    expected = [('erase', [0x7e0000, ERASE_BYTES]), ('write', [0x7e0000, 0x83000000, image['bytes']])]
    require(len(mutations) == len(expected), 'unexpected flash mutation count')
    for (operation, arguments), (expected_operation, expected_values) in zip(mutations, expected):
        fields = arguments.strip().split()
        require(operation == expected_operation and len(fields) == len(expected_values)
            and all(re.fullmatch(r'0x[0-9a-fA-F]+', field) for field in fields),
            'flash command shape mismatch')
        require([int(field, 16) for field in fields] == expected_values, 'out-of-scope flash command')
    require(not re.search(r'(?im)(?:^|>|;)\s*(?:saveenv|setenv|bootenv\s+set|sf\s+(?:erase|write))\b', trace),
        'unexpected environment or alternate flash write')
    markers = (
        'MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc=',
        'current_live_crc=' + current['full_slot_crc32'],
        'OMF321_ERASED_PREFIX_CRC_PASS=1 bytes=6160384 crc=aa86bf2e',
        'PROTECTED_PARTITION_CRC_PASS=1',
        'MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc=' + image['full_slot_crc32'] + ' prefix=identical',
        'MTD4_FLASH_AND_READBACK_PASS=1 candidate=' + image['sha256'],
        'candidate_transport=uart-ymodem',
    )
    cursor = 0
    for marker in markers:
        index = backend.find(marker, cursor)
        require(index >= 0, 'missing or out-of-order backend proof marker')
        cursor = index + len(marker)
    return {'status': 'PASS_VERIFIED_ETHERNET_WRITER', 'candidate_sha256_expected': image['sha256'],
        'ram_load': ram_proof, 'flash_control_transport': 'uart-bootbase',
        'legacy_backend_transport_label': 'uart-ymodem: fixed preloaded-branch label, not bulk-transport evidence',
        'full_slot_sha256_expected_local': image['full_slot_sha256'], 'full_slot_sha256_observed': None,
        'full_slot_crc32_observed': image['full_slot_crc32'],
        'current_prewrite_crc32_observed': current['full_slot_crc32'],
        'candidate_prefix_compared_bytes': image['bytes'], 'protected_partitions_crc_verified': True}


def run_preloaded_handoff(*, direction: str, server_ipv4: str, network_authorized: bool,
                          load_ram, loader_closed, guard, writer, all_children_stopped) -> dict:
    """Dependency-injected flow; never owns/relinquishes a lease or retries.

    Callbacks must be supplied by a separately reviewed physical adapter. `writer`
    returns a fresh attempt directory with the new evidence schema above. A
    verified writer is not platform/UI acceptance and does not trigger recovery
    here. Unknown child state propagates as `retain_lease_required`.
    """
    result = {'schema': 'openmitrastar.f323-ethernet-handoff/v1', 'status': 'STOP_NO_AUTOMATIC_RETRY',
        'ram_verified': False, 'writer_started': False, 'writer_verified': False,
        'retain_lease_required': False, 'physical_adapters_qualified_by_this_module': False,
        'automatic_recovery_started': False, 'release_eligible': False}
    started = False
    stage = 'scope-and-network-authority'
    try:
        image, current = exact_pair(direction)
        server_ipv4 = exact_server(server_ipv4)
        require(network_authorized is True, 'network authority not granted')
        # The guard may itself start a bounded verification helper. Its failure
        # does not establish helper termination; check containment on that path.
        started = True
        stage = 'guard-before-ram'
        require(guard() is True, 'live guard did not pass before RAM phase')
        stage = 'ram-loader'
        ram = load_ram()
        stage = 'ram-proof'
        proof = validate_ram_result(ram, direction=direction, server_ipv4=server_ipv4)
        stage = 'loader-closure'
        require(loader_closed() is True, 'loader closure unproved before writer')
        result['ram_verified'] = True
        result['ram_load'] = proof
        stage = 'guard-before-writer'
        require(guard() is True, 'live guard did not pass before writer')
        result['writer_started'] = True
        stage = 'writer'
        directory = writer(image=image, current=current, skip_reboot=True, skip_network_transfer=True)
        stage = 'writer-proof'
        # Compare the same RAM bytes whose evidence hash was verified, rather
        # than reading the file again after checking its binding.
        result['writer'] = verify_writer_result(directory, direction=direction, server_ipv4=server_ipv4,
            expected_ram_result=ram)
        result['writer_verified'] = True
        result['status'] = 'PASS_ETHERNET_RAM_TO_WRITER_HANDOFF'
    except Exception as error:
        result['error_type'] = type(error).__name__  # Never echo callbacks/packet contents.
        result['failed_stage'] = stage
    finally:
        if started:
            try:
                contained = all_children_stopped() is True
            except Exception:
                contained = False
            if not contained:
                result.update(status='STOP_NO_AUTOMATIC_RETRY', retain_lease_required=True,
                    writer_verified=False, containment_verified=False)
                result.setdefault('failed_stage', 'helper-containment')
            else:
                result['containment_verified'] = True
    return result
