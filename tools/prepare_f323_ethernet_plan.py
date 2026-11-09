"""File-only Ethernet/TFTP preparation. No execute mode or network mutation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import sys

import f323_execution_contract as uart_contract


AUTHORIZATION = uart_contract.ROOT / 'outputs/authorizations/f323-20260911T153634Z/authorization.json'
AUTHORIZATION_SHA = 'ba0cab09d491b2b6080dd27963c2812fbe2810963d7dc324ae102e36a35aeb2e'


def validate_recorded_authorization(path: Path = AUTHORIZATION, expected_sha: str = AUTHORIZATION_SHA) -> dict:
    """Verify the existing firmware-only record; never infer transport authority."""
    if uart_contract.digest(path) != expected_sha:
        raise ValueError('recorded firmware authorization hash mismatch')
    record = uart_contract.read_json(path)
    expected = {'schema': 'openmitrastar.owner-authorization/v1',
        'target_model': 'HGW-500BNA-QCv2 A2', 'target_host': uart_contract.HOST,
        'candidate_sha256': uart_contract.F323['sha256'], 'candidate_bytes': uart_contract.F323['bytes'],
        'write_target': 'mtd4/linux_live', 'erase_bytes': uart_contract.ERASE_BYTES,
        'slot_bytes': uart_contract.SLOT_BYTES, 'recovery_f321_sha256': uart_contract.F321['sha256'],
        'protected_partitions': ['mtd0', 'mtd1', 'mtd2', 'mtd3', 'mtd5']}
    if (any(record.get(key) != value for key, value in expected.items())
        or record.get('authorized') is not True
        or record.get('fallback_f314_authorized_by_this_reply') is not False
        or record.get('boot_environment_changes') is not False
        or record.get('radio_configuration_changes') is not False):
        raise ValueError('recorded firmware authorization scope mismatch')
    return {'path': str(path.resolve()), 'sha256': expected_sha,
        'scope': 'exact F323 mtd4 installation and conditional F321 recovery only',
        'new_network_authority': False}


def network_scope(snapshot: dict) -> dict:
    if (snapshot.get("schema") != "openmitrastar.f323-network-readonly/v1"
        or snapshot.get("target") != uart_contract.HOST
        or snapshot.get("network_mutation") is not False):
        raise ValueError("network snapshot does not identify the read-only HGW scope")
    source=ipaddress.IPv4Address(snapshot["source_ipv4"])
    target=ipaddress.IPv4Address(uart_contract.HOST)
    subnet=ipaddress.IPv4Network(snapshot["target_route_prefix"],strict=False)
    if (not source.is_private or source.is_unspecified or source.is_loopback or source.is_link_local
        or source.is_multicast or source==target or source not in subnet or target not in subnet
        or source in (subnet.network_address,subnet.broadcast_address)):
        raise ValueError("source/interface subnet is not an explicit private peer route")
    if snapshot.get("target_next_hop") != "0.0.0.0" or snapshot.get("media_type") != "802.3":
        raise ValueError("the prepared path must be direct-route Ethernet")
    if type(snapshot.get("interface_index")) is not int or snapshot["interface_index"] <= 0:
        raise ValueError("invalid interface binding")
    if snapshot.get("udp69_listeners") != []:
        raise ValueError("UDP/69 is occupied or its state is unknown; never stop its owner")
    return {"server_ipv4":str(source),"client_ipv4":str(target),"interface_index":snapshot["interface_index"],
        "interface_alias":snapshot["interface_alias"],"network_category":snapshot.get("network_category"),
        "shared_default_route":bool(snapshot.get("default_routes_on_interface")),
        "isolated_link_proven":snapshot.get("isolated_link_proven") is True,
        "host_address_or_route_changes_allowed":False}


def make_plan(snapshot: dict) -> dict:
    network=network_scope(snapshot)
    image=uart_contract.F323
    return {"schema":"openmitrastar.f323-ethernet-preparation/v1",
        "status":"NO_GO_NETWORK_SCOPE_AND_EXECUTOR_REVIEW_PENDING",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),"mode":"file-only",
        "target_model":"HGW-500BNA-QCv2 A2","target_host":uart_contract.HOST,
        "candidate":str(uart_contract.image_path(image)),"candidate_sha256":image["sha256"],"candidate_bytes":image["bytes"],
        "same_firmware_image":True,"network":network,
        "server":{"implementation":"tools/f323_scoped_tftp.py","bind":network["server_ipv4"],"port":69,
            "allowed_client":uart_contract.HOST,"allowed_filename":uart_contract.image_path(image).name,
            "read_only":True,"one_transfer":True,"global_timeout_seconds":300,
            "immutable_hash_verified_payload":True,"other_files_or_directory_listing":False,
            "uploads_wrq":False,"transport_encrypted":False,
            "data_source_port":"ephemeral, pinned per accepted transfer",
            "start_point":"after slow prewrite checks, immediately before the single transfer",
            "physical_compatibility_verified":False},
        "host_firewall":{"change_performed":False,"disable_firewall_allowed":False,
            "udp_data_return_path_review_required":True,
            "proposed_rule_covers":"RRQ listener only; UDP return path is not qualified by this plan",
            "proposed_rule_if_authorized":{"direction":"inbound","protocol":"UDP","local_port":69,
                "local_address":network["server_ipv4"],"remote_address":uart_contract.HOST,
                "interface_index":network["interface_index"],"program":sys.executable,
                "temporary":True,"remove_only_this_run_rule":True}},
        "bootloader":{"bulk_transport":"Ethernet/TFTP","control_transport":"verified UART",
            "changes_performed":False,"planned_volatile_variables":{"ipaddr":uart_contract.HOST,"serverip":network["server_ipv4"]},
            "saveenv_allowed":False,"bootcmd_or_bootselect_change_allowed":False,
            "ram_load_address":"0x83000000","ram_integrity_before_flash_required":True},
        "firmware_write":{"performed":False,"target":"mtd4/linux_live","offset":"0x007e0000",
            "erase_bytes":uart_contract.ERASE_BYTES,"slot_bytes":uart_contract.SLOT_BYTES,
            "protected_partitions":["mtd0","mtd1","mtd2","mtd3","mtd5"],"logical_mtd6_write_allowed":False,
            "recovery_image_sha256":uart_contract.F321["sha256"],
            "recovery_condition":"only after verified writer and failed postgate; no ambiguous-write retry"},
        "authority":{"firmware_authorization_record":"outputs/authorizations/f323-20260911T153634Z/authorization.json",
            "exact_firmware_authorization_already_recorded":None,
            "record_verified_in_this_plan":False,
            "ethernet_private_image_exposure_authorized":False,
            "temporary_firewall_rule_authorized":False,
            "volatile_bootloader_network_parameters_authorized":False,
            "existing_uart_executor_review_qualifies_tftp":False},
        "warnings":[
            "The image contains private device identity. TFTP is plaintext and source-IP filtering is not authentication or proof of isolation.",
            "The observed Ethernet carries the PC default route; do not disconnect, readdress or change routes automatically.",
            "The observed Public firewall profile does not itself mean Internet exposure; an exact temporary peer/program rule must be reviewed if required.",
            "Linux-to-host RX smoke success does not qualify bulk YMODEM, host TX or Bootbase Ethernet."],
        "still_required":["new exact Ethernet executor, UDP return path and recovery review",
            "owner decision for private-image LAN exposure and temporary networking scope","fresh topology and occupancy revalidation",
            "fresh exclusive lease and authenticated UART board binding","Bootbase current/protected checks, RAM verification, write/readback and platform/UI gates"],
        "hardware_actions_performed":False,"network_listener_started":False,"release_eligible":False}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network-snapshot',required=True,type=Path)
    parser.add_argument('--network-snapshot-sha256',required=True)
    parser.add_argument('--output-dir',required=True,type=Path)
    args=parser.parse_args()
    if uart_contract.digest(args.network_snapshot) != args.network_snapshot_sha256:
        raise ValueError('network snapshot hash mismatch')
    authorization = validate_recorded_authorization()
    uart_contract.validate_sealed_inputs()
    plan=make_plan(uart_contract.read_json(args.network_snapshot))
    plan['authority'].update(exact_firmware_authorization_already_recorded=True,
        record_verified_in_this_plan=True, verified_record=authorization)
    plan['network_observation']={'path':str(args.network_snapshot.resolve()),'sha256':args.network_snapshot_sha256}
    args.output_dir.mkdir(parents=True,exist_ok=False)
    (args.output_dir/'plan.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='ascii')
    print(json.dumps(plan,indent=2))


if __name__=='__main__':
    main()
