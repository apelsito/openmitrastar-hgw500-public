"""Pure Ethernet-scope checks, without opening sockets or contacting hardware."""
import copy
import hashlib
import json

import pytest

from prepare_f325_ethernet_plan import make_plan, network_scope, validate_recorded_authorization


def snapshot():
    return {'schema':'openmitrastar.f325-network-readonly/v1','target':'192.168.1.90','network_mutation':False,
        'source_ipv4':'192.168.1.249','target_route_prefix':'192.168.1.0/24','target_next_hop':'0.0.0.0',
        'media_type':'802.3','interface_index':15,'interface_alias':'Ethernet','network_category':'Public',
        'default_routes_on_interface':[{'NextHop':'192.168.1.1'}],'udp69_listeners':[],'isolated_link_proven':False}


def test_preparation_is_not_authority_or_live_readiness():
    plan=make_plan(snapshot())
    assert plan['network']['server_ipv4']=='192.168.1.249'
    assert plan['network']['shared_default_route'] is True
    assert plan['network']['isolated_link_proven'] is False
    assert plan['authority']['ethernet_private_image_exposure_authorized'] is False
    assert plan['authority']['existing_uart_executor_review_qualifies_tftp'] is False
    assert plan['authority']['exact_firmware_authorization_already_recorded'] is None
    assert plan['authority']['record_verified_in_this_plan'] is False
    assert plan['network_listener_started'] is False and plan['hardware_actions_performed'] is False
    assert plan['firmware_write']['performed'] is False and plan['release_eligible'] is False


@pytest.mark.parametrize('address',['0.0.0.0','127.0.0.1','192.168.1.90','192.168.2.249','192.168.1.0','192.168.1.255','8.8.8.8','224.0.0.1'])
def test_unscoped_wrong_or_nonpeer_source_is_refused(address):
    value=snapshot();value['source_ipv4']=address
    with pytest.raises(ValueError):network_scope(value)


@pytest.mark.parametrize('key,value',[('target','192.168.1.1'),('network_mutation',True),('target_next_hop','192.168.1.1'),
    ('media_type','802.11'),('interface_index',0),('interface_index',True),('udp69_listeners',[{'OwningProcess':123}]),('udp69_listeners',None)])
def test_incompatible_or_unknown_topology_is_refused(key,value):
    data=copy.deepcopy(snapshot());data[key]=value
    with pytest.raises(ValueError):network_scope(data)


def test_scope_preserves_protected_partitions_and_boot_selection():
    plan=make_plan(snapshot())
    assert plan['server']['allowed_client']=='192.168.1.90'
    assert plan['server']['uploads_wrq'] is False and plan['server']['other_files_or_directory_listing'] is False
    assert plan['bootloader']['saveenv_allowed'] is False and plan['bootloader']['bootcmd_or_bootselect_change_allowed'] is False
    assert plan['network']['host_address_or_route_changes_allowed'] is False
    assert plan['firmware_write']['protected_partitions']==['mtd0','mtd1','mtd2','mtd3','mtd5']
    assert plan['firmware_write']['erase_bytes']==0x5e0000
    assert plan['host_firewall']['udp_data_return_path_review_required'] is True


def authorization_record():
    return {'schema':'openmitrastar.owner-authorization/v1','authorized':True,
        'target_model':'HGW-500BNA-QCv2 A2','target_host':'192.168.1.90',
        'candidate_sha256':'e18b221dda9a61bd1066c155c0cd7b44aef0d0fe06b1a1752a7e759e7730c7ec',
        'candidate_bytes':5332992,'write_target':'mtd4/linux_live','erase_bytes':0x5e0000,'slot_bytes':0x7a0000,
        'recovery_f321_sha256':'eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18',
        'protected_partitions':['mtd0','mtd1','mtd2','mtd3','mtd5'],
        'fallback_f314_authorized_by_this_reply':False,'boot_environment_changes':False,
        'radio_configuration_changes':False}


def write_record(tmp_path, value):
    path = tmp_path / 'synthetic-authorization.json'
    data = json.dumps(value).encode('ascii')
    path.write_bytes(data)
    return path, hashlib.sha256(data).hexdigest()


def test_existing_exact_authorization_is_bound_without_new_transport_authority(tmp_path):
    path, digest = write_record(tmp_path, authorization_record())
    proof = validate_recorded_authorization(path, digest)
    assert proof['sha256'] == digest and proof['path'] == str(path.resolve())
    assert proof['new_network_authority'] is False


def test_changed_authorization_bytes_are_rejected(tmp_path):
    path, _ = write_record(tmp_path, authorization_record())
    with pytest.raises(ValueError, match='hash mismatch'):
        validate_recorded_authorization(path, '0' * 64)


@pytest.mark.parametrize('key,value', [('authorized',False),('authorized',1),('target_host','192.168.1.1'),
    ('candidate_sha256','0'*64),('candidate_bytes',5361665),('write_target','mtd3/linux_safety'),
    ('erase_bytes',0x7a0000),('recovery_f321_sha256','0'*64),('protected_partitions',[]),
    ('fallback_f314_authorized_by_this_reply',True),('boot_environment_changes',True),
    ('radio_configuration_changes',True)])
def test_inapplicable_authorization_cannot_be_asserted_even_with_rehashed_fixture(tmp_path,key,value):
    record = authorization_record(); record[key] = value
    path, digest = write_record(tmp_path, record)
    with pytest.raises(ValueError, match='scope mismatch'):
        validate_recorded_authorization(path, digest)
