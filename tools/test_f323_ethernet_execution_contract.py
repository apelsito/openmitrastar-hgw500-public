"""File-only Ethernet contract tests; no native or hardware entrypoint."""
import copy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

import f323_ethernet_execution_contract as contract


@pytest.fixture
def fake_base(monkeypatch):
    monkeypatch.setattr(contract.base, 'plan', lambda direction: {'direction':direction,
        'local_preflight_pass':True,'physical_authorization':False,'hardware_actions_performed':False})
    monkeypatch.setattr(contract.base, 'generic_preflight', lambda image,current: {
        'candidate_sha256':image['sha256'],'write_transport':'UART Bootbase + YMODEM'})


def test_missing_network_authority_never_becomes_physical_permission(fake_base):
    plan = contract.plan('promote')
    assert plan['network_authorization_verified'] is False
    assert plan['executor_review_verified'] is False
    assert plan['hardware_actions_performed'] is False
    assert plan['physical_authorization'] is False
    assert plan['transport'] == 'ethernet-tftp'
    assert 'YMODEM' not in plan['preflight']['write_transport']


def test_exact_existing_owner_network_record_is_accepted_without_asking_again():
    proof = contract.validate_network_authorization(contract.AUTHORIZATION,contract.AUTHORIZATION_SHA,
        server_ipv4='192.168.1.249',interface_index=15)
    assert proof['sha256'] == contract.AUTHORIZATION_SHA


@pytest.mark.parametrize('field,value',[('server_ipv4','192.168.1.248'),('server_ipv4','8.8.8.8'),
    ('interface_index',16),('interface_index',True)])
def test_owner_record_cannot_be_used_for_another_network(field,value):
    kwargs = dict(server_ipv4='192.168.1.249',interface_index=15)
    kwargs[field] = value
    with pytest.raises(ValueError):
        contract.validate_network_authorization(contract.AUTHORIZATION,contract.AUTHORIZATION_SHA,**kwargs)


def test_firmware_only_approval_is_not_reinterpreted_as_network_permission():
    with pytest.raises(ValueError):
        contract.validate_network_authorization(contract.ROOT/'outputs/authorizations/f323-20260911T153634Z/authorization.json',
            'ba0cab09d491b2b6080dd27963c2812fbe2810963d7dc324ae102e36a35aeb2e',server_ipv4='192.168.1.249',interface_index=15)


@pytest.mark.parametrize('patch',[{'authorized':1},{'saveenv_authorized':True},
    {'host_address_or_route_changes_authorized':True},{'automatic_f314_fallback_authorized':True},
    {'target_host':'192.168.1.1'},{'plaintext_private_image_transfer_authorized':False}])
def test_wrong_authorization_semantics_refused_even_in_rehashed_synthetic_fixture(tmp_path,monkeypatch,patch):
    value = contract.read_json(contract.AUTHORIZATION)
    value.update(patch)
    path = tmp_path/'synthetic-record.json'
    path.write_text(json.dumps(value),encoding='utf-8')
    digest = contract.base.digest(path)
    monkeypatch.setattr(contract,'AUTHORIZATION_SHA',digest)
    with pytest.raises(ValueError):
        contract.validate_network_authorization(path,digest,server_ipv4='192.168.1.249',interface_index=15)


def test_record_and_review_are_distinct_gates(fake_base,monkeypatch):
    monkeypatch.setattr(contract,'validate_executor_review',lambda *_: {})
    plan = contract.plan('promote',Path('synthetic-review.json'),'a'*64,
        contract.AUTHORIZATION,contract.AUTHORIZATION_SHA)
    assert plan['executor_review_verified'] is True and plan['network_authorization_verified'] is True
    assert plan['hardware_actions_performed'] is False and plan['physical_authorization'] is False
    assert plan['network']['python_executable'] == str(Path(contract.sys.executable).resolve())


@pytest.mark.parametrize('kwargs',[{'review_path':Path('x')},{'review_sha':'a'*64},
    {'network_authorization_path':Path('x')},{'network_authorization_sha':'a'*64}])
def test_path_without_hash_or_hash_without_path_is_refused_before_preflight(fake_base,kwargs):
    with pytest.raises(ValueError): contract.plan('promote',**kwargs)


def test_no_f314_or_arbitrary_direction(fake_base):
    with pytest.raises(ValueError): contract.plan('fallback')


def make_tests(path, *, missing_module=False, failed=False):
    root = ET.Element('testsuites'); suite = ET.SubElement(root,'testsuite')
    modules = sorted(contract.REQUIRED_TEST_MODULES)
    if missing_module: modules.pop()
    names = sorted(contract.REQUIRED_BEHAVIOR_GATES)
    for index in range(30):
        name = names[index] if index < len(names) else f'synthetic_{index}'
        case = ET.SubElement(suite,'testcase',{'name':name,'classname':modules[index%len(modules)]})
        if failed and index==0: ET.SubElement(case,'failure')
    ET.ElementTree(root).write(path,encoding='utf-8')


def test_full_qualification_requires_all_three_integration_modules_and_all_pass(tmp_path):
    path = tmp_path/'synthetic.xml'
    make_tests(path); assert contract.qualify_report(path)==30
    make_tests(path,missing_module=True)
    with pytest.raises(ValueError): contract.qualify_report(path)
    make_tests(path,failed=True)
    with pytest.raises(ValueError): contract.qualify_report(path)


def test_component_qualification_hashes_and_sources_still_match():
    assert len(contract.validate_prerequisites()) == 3


def test_qualification_requires_named_safety_behaviors(tmp_path):
    path = tmp_path/'synthetic.xml'
    make_tests(path)
    tree = ET.parse(path)
    tree.find('.//testcase').set('name','unrelated')
    tree.write(path,encoding='utf-8')
    with pytest.raises(ValueError): contract.qualify_report(path)


def test_duplicate_record_keys_are_rejected(tmp_path):
    path = tmp_path/'synthetic.json'
    path.write_text('{"authorized":false,"authorized":true}',encoding='ascii')
    with pytest.raises(ValueError): contract.read_json(path)
