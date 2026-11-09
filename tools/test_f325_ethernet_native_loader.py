"""Composition checks with fake adapters/payload; no network or hardware."""
from unittest.mock import Mock

import pytest

import f325_ethernet_native_loader as loader
from f325_ethernet_handoff import CRCS


@pytest.fixture
def rig(tmp_path, monkeypatch):
    loaded = Mock(return_value=object())
    validated = Mock()
    monkeypatch.setattr(loader, 'load_verified_file', loaded)
    monkeypatch.setattr(loader, 'validate_payload', validated)
    guard = Mock(return_value=True)
    guard.close_all.return_value = True
    channel = Mock()
    channel.close.return_value = True
    server = Mock()
    server.close.return_value = True
    constructors = [Mock(return_value=value) for value in (guard, channel, server)]
    for name, factory in zip(('InheritedPhysicalGuard', 'BoundedUartChannel', 'ScopedTftpProcess'), constructors):
        monkeypatch.setattr(loader, name, factory)
    image, _ = loader.exact_pair('promote')
    ram = {'schema': 'openmitrastar.f325-ethernet-ram-gate/v1', 'status': 'PASS_ETHERNET_RAM_GATE',
        'candidate_sha256': image['sha256'], 'candidate_bytes': image['bytes'],
        'candidate_crc32': CRCS[image['sha256']], 'address': '0x83000000', 'server_closed': True,
        'flash_writes': 0, 'server_result': {'schema': 'openmitrastar.f325-scoped-tftp/v1',
            'status': 'PASS_TFTP_SINGLE_TRANSFER', 'transfer_started': True, 'transfer_complete': True,
            'sockets_closed': True, 'flash': False, 'boot_verified': False, 'bind': '192.168.1.249',
            'allow_client': '192.168.1.90', 'port': 69, 'allow_file': image['base'] + '.webformat.bin',
            'file': {'sha256': image['sha256'], 'bytes': image['bytes']},
            'counts': {'payload_bytes_acked': image['bytes'], 'blocks_acked': image['bytes'] // 512 + 1}}}
    protocol = Mock(return_value=ram)
    monkeypatch.setattr(loader, 'run_ram_gate', protocol)
    options = dict(direction='promote', server_ipv4='192.168.1.249', output_dir=tmp_path / 'attempt',
        execute=True, network_authorized=True, parent_review_verified=True)
    return dict(options=options, loaded=loaded, guard=guard, channel=channel, server=server,
        constructors=constructors, protocol=protocol, ram=ram)


@pytest.mark.parametrize('key,value', [('execute',False), ('network_authorized',False),
    ('network_authorized',1), ('parent_review_verified',False), ('parent_review_verified',1)])
def test_inert_or_unqualified_request_has_no_file_native_or_payload_access(rig,key,value):
    rig['options'][key] = value
    result = loader.run_native_ram_load(**rig['options'])
    assert not result['writer_ready']
    assert not rig['options']['output_dir'].exists()
    rig['loaded'].assert_not_called()
    for factory in rig['constructors']:
        factory.assert_not_called()


def test_all_adapters_compose_and_evidence_precedes_success(rig):
    result = loader.run_native_ram_load(**rig['options'])
    assert result['status'] == 'PASS_NATIVE_ETHERNET_RAM_LOAD' and result['ram_handoff_ready']
    assert result['writer_ready'] is False  # Only the parent can observe loader exit.
    assert result['native_cleanup_verified'] and not result['retain_lease_required']
    rig['channel'].open.assert_called_once()
    rig['channel'].acquire_prompt.assert_called_once()
    rig['protocol'].assert_called_once()
    for actor, method in ((rig['server'],'close'),(rig['channel'],'close'),(rig['guard'],'close_all')):
        getattr(actor, method).assert_called_once()
    assert {p.name for p in rig['options']['output_dir'].iterdir()} == {
        'ethernet-ram-result.json','ethernet-server-result.json','native-loader-result.json'}
    assert result['loader_process_exit_observed_by_parent'] is False
    assert result['flash_written'] is False and result['rebooted'] is False


@pytest.mark.parametrize('failed_stage', ['payload', 'guard', 'open', 'attach', 'protocol', 'incomplete-pass'])
def test_prewrite_failures_never_yield_writer_ready_and_all_cleanup_runs(rig,failed_stage):
    if failed_stage == 'payload': rig['loaded'].side_effect = RuntimeError('PRIVATE_ERROR')
    elif failed_stage == 'guard': rig['guard'].return_value = False
    elif failed_stage == 'open': rig['channel'].open.side_effect = RuntimeError('PRIVATE_ERROR')
    elif failed_stage == 'attach': rig['channel'].acquire_prompt.side_effect = RuntimeError('PRIVATE_ERROR')
    elif failed_stage == 'protocol': rig['protocol'].return_value = {'status':'FAIL_ETHERNET_RAM_GATE'}
    else: rig['protocol'].return_value = {'status':'PASS_ETHERNET_RAM_GATE'}
    result = loader.run_native_ram_load(**rig['options'])
    assert result['status'] == 'STOP_NO_AUTOMATIC_RETRY' and not result['writer_ready']
    assert 'PRIVATE_ERROR' not in str(result)
    if failed_stage != 'payload':
        rig['server'].close.assert_called_once()
        rig['channel'].close.assert_called_once()
        rig['guard'].close_all.assert_called_once()


@pytest.mark.parametrize('actor,method', [('server','close'),('channel','close'),('guard','close_all')])
def test_one_cleanup_failure_still_cleans_others_and_requires_lease_retention(rig,actor,method):
    getattr(rig[actor],method).side_effect = RuntimeError('PRIVATE_ERROR')
    result = loader.run_native_ram_load(**rig['options'])
    assert result['retain_lease_required'] and not result['writer_ready'] and not result['ram_handoff_ready']
    assert not result['native_cleanup_verified']
    rig['server'].close.assert_called_once()
    rig['channel'].close.assert_called_once()
    rig['guard'].close_all.assert_called_once()


def test_evidence_failure_cannot_return_success(rig,monkeypatch):
    monkeypatch.setattr(loader,'write_once',Mock(side_effect=OSError('PRIVATE_ERROR')))
    result = loader.run_native_ram_load(**rig['options'])
    assert result['status'] == 'STOP_NO_AUTOMATIC_RETRY'
    assert result['evidence_write_failed'] and not result['writer_ready'] and not result['ram_handoff_ready']


def test_existing_output_directory_is_preserved_before_guard(rig):
    rig['options']['output_dir'].mkdir()
    marker = rig['options']['output_dir'] / 'owner-file.txt'
    marker.write_text('preserve',encoding='ascii')
    result = loader.run_native_ram_load(**rig['options'])
    assert result['status'] == 'STOP_NO_AUTOMATIC_RETRY'
    assert marker.read_text() == 'preserve'
    for factory in rig['constructors']:
        factory.assert_not_called()
