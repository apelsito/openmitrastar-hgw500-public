"""Compose the bounded adapters under a separately reviewed parent Job/lease.

No CLI and no reboot/flash. Defaults are inert. The qualified parent must bind
the exact source review and owner network record before setting either permit,
prove the live board identity, and stop the already-owned HGW at Topaz. A true
boolean here does not create that authority. The caller must also observe this
loader process exiting before opening the preloaded flash backend.
"""
from __future__ import annotations

import json
from pathlib import Path

from f325_execution_contract import image_path
from f325_ethernet_guard_process import InheritedPhysicalGuard
from f325_ethernet_handoff import exact_pair, exact_server, validate_ram_result
from f325_ethernet_ram_gate import PASS, run_ram_gate, validate_payload
from f325_ethernet_server_process import ScopedTftpProcess
from f325_ethernet_uart import BoundedUartChannel
from f325_scoped_tftp import load_verified_file, new_output_directory


def write_once(path: Path, value: dict):
    with path.open('x', encoding='ascii', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + '\n')


def run_native_ram_load(*, direction: str, server_ipv4: str, output_dir: Path,
                        execute: bool = False, network_authorized: bool = False,
                        parent_review_verified: bool = False) -> dict:
    image, _ = exact_pair(direction)
    server_ipv4 = exact_server(server_ipv4)
    result = {'schema': 'openmitrastar.f325-native-ethernet-load/v1', 'status': 'DRY_RUN',
        'candidate_sha256': image['sha256'], 'candidate_bytes': image['bytes'],
        'target_host': '192.168.1.90', 'server_ipv4': server_ipv4,
        'writer_ready': False, 'ram_handoff_ready': False, 'retain_lease_required': False, 'flash_written': False,
        'rebooted': False, 'host_network_or_firewall_changed': False,
        'loader_process_exit_observed_by_parent': False,
        'parent_execution_review_verified': parent_review_verified is True,
        'raw_uart_or_guard_output_logged': False, 'ram_result': None}
    if execute is not True:
        return result
    if network_authorized is not True or parent_review_verified is not True:
        result.update(status='REFUSED_BEFORE_NATIVE_ACTIONS', failed_stage='network-authority-or-parent-review')
        return result

    stage = 'sealed-payload'
    directory = None
    guard = channel = server = None
    result['status'] = 'STOP_NO_AUTOMATIC_RETRY'
    try:
        payload = load_verified_file(image_path(image), image['sha256'], image['bytes'])
        validate_payload(payload)
        directory = new_output_directory(output_dir)
        stage = 'native-adapter-construction'
        guard = InheritedPhysicalGuard(direction=direction, network_authorized=True)
        channel = BoundedUartChannel(direction=direction, server_ipv4=server_ipv4,
            guard=guard, network_authorized=True)
        server = ScopedTftpProcess(guard=guard, output_dir=directory / 'tftp-process')
        stage = 'inherited-physical-guard'
        if guard() is not True:
            raise RuntimeError('physical_guard_unconfirmed')
        stage = 'uart-open'
        channel.open()
        stage = 'topaz-attach'
        channel.acquire_prompt()
        stage = 'ethernet-ram-protocol'
        result['ram_result'] = run_ram_gate(channel=channel, server=server, payload=payload,
            server_ipv4=server_ipv4, client_ipv4='192.168.1.90', guard=guard,
            network_authorized=True)
        if result['ram_result'].get('status') != PASS:
            raise RuntimeError('ram_protocol_did_not_pass')
        validate_ram_result(result['ram_result'], direction=direction, server_ipv4=server_ipv4)
        result['status'] = 'PASS_NATIVE_ETHERNET_RAM_LOAD'
    except Exception as error:
        result['status'] = 'STOP_NO_AUTOMATIC_RETRY'
        result['failed_stage'] = stage
        result['error_type'] = type(error).__name__
    finally:
        cleanup = {}
        for name, item, method in (('server', server, 'close'), ('uart', channel, 'close'),
                                   ('guard_helpers', guard, 'close_all')):
            try:
                cleanup[name] = item is None or getattr(item, method)() is True
            except Exception:
                cleanup[name] = False
        result['cleanup'] = cleanup
        result['native_cleanup_verified'] = all(cleanup.values())
        if not result['native_cleanup_verified']:
            result.update(status='STOP_NO_AUTOMATIC_RETRY', retain_lease_required=True)
            result.setdefault('failed_stage', 'native-cleanup')
        # A child cannot observe its own terminal process state. Only the parent
        # can combine this RAM handoff with process/Job closure and permit write.
        result['ram_handoff_ready'] = (result['status'] == 'PASS_NATIVE_ETHERNET_RAM_LOAD'
                                       and result['native_cleanup_verified'])
        if directory is not None:
            try:
                ram = result['ram_result']
                if ram is not None:
                    write_once(directory / 'ethernet-ram-result.json', ram)
                    if isinstance(ram.get('server_result'), dict):
                        write_once(directory / 'ethernet-server-result.json', ram['server_result'])
                write_once(directory / 'native-loader-result.json', result)
            except Exception:
                # Evidence loss cannot leave a successful return value that a
                # parent might feed to the flash backend.
                result.update(status='STOP_NO_AUTOMATIC_RETRY', writer_ready=False, ram_handoff_ready=False,
                    evidence_write_failed=True)
    return result
