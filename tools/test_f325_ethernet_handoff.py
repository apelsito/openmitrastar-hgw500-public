"""File-only handoff tests using synthetic metadata and callback implementations.

No server, socket, serial port, subprocess or firmware image is opened. The
candidate constants identify expected contracts; all files below are temporary
JSON/text fixtures, never image payloads or real attempt evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import f325_ethernet_handoff as handoff


SERVER = "192.168.1.249"


def ram_result(direction="promote", server=SERVER):
    image, _ = handoff.exact_pair(direction)
    return {
        "schema": handoff.RAM_SCHEMA, "status": "PASS_ETHERNET_RAM_GATE",
        "candidate_sha256": image["sha256"], "candidate_bytes": image["bytes"],
        "candidate_crc32": handoff.CRCS[image["sha256"]], "address": "0x83000000",
        "server_closed": True, "flash_writes": 0,
        "server_result": {
            "schema": "openmitrastar.f325-scoped-tftp/v1", "status": "PASS_TFTP_SINGLE_TRANSFER",
            "transfer_started": True, "transfer_complete": True, "sockets_closed": True,
            "flash": False, "boot_verified": False, "bind": server,
            "allow_client": "192.168.1.90", "port": 69,
            "allow_file": image["base"] + ".webformat.bin",
            "file": {"sha256": image["sha256"], "bytes": image["bytes"]},
            "counts": {"payload_bytes_acked": image["bytes"], "blocks_acked": image["bytes"] // 512 + 1},
        },
    }


def make_bundle(tmp_path: Path, direction="promote"):
    image, current = handoff.exact_pair(direction)
    directory = tmp_path / "attempt"
    directory.mkdir(parents=True)
    result = {
        "schema": handoff.WRITER_SCHEMA, "status": "PASS", "candidate_sha256": image["sha256"],
        "physical_write": {"offset": 0x7e0000, "erase_size": handoff.ERASE_BYTES,
                           "candidate_size": image["bytes"], "slot_size": handoff.SLOT_BYTES,
                           "partition": "mtd4/linux_live"},
        "backend_sha256": handoff.BACKEND_SHA256,
        "flash": {"control_transport": "uart-bootbase", "network_transfer_performed": False,
                  "skip_reboot": True, "skip_network_transfer": True},
        "readback": {"full_slot_crc32": image["full_slot_crc32"], "candidate_prefix_compare": "PASS"},
        "protected_partitions": {"status": "PASS"},
    }
    trace = (
        f"topaz>spi_flash erase 0x007e0000 0x{handoff.ERASE_BYTES:08x}\n"
        f"topaz>spi_flash write 0x007e0000 0x83000000 0x{image['bytes']:08x}\n"
        f"Total of {image['bytes']} bytes were the same\n"
    )
    backend = (
        "MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc=d6b13baa "
        f"current_live_crc={current['full_slot_crc32']}\n"
        "OMF321_ERASED_PREFIX_CRC_PASS=1 bytes=6160384 crc=aa86bf2e\n"
        "PROTECTED_PARTITION_CRC_PASS=1\n"
        f"MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc={image['full_slot_crc32']} prefix=identical\n"
        f"MTD4_FLASH_AND_READBACK_PASS=1 candidate={image['sha256']} candidate_transport=uart-ymodem\n"
    )
    bundle = {"directory": directory, "direction": direction, "image": image, "current": current,
              "result": result, "ram": ram_result(direction), "trace": trace, "backend": backend}
    save_bundle(bundle)
    return bundle


def save_result(bundle):
    (bundle["directory"] / "result.json").write_text(json.dumps(bundle["result"]), encoding="ascii")


def save_bundle(bundle):
    files = {
        "bootbase-flash-uart.log": bundle["trace"], "backend.log": bundle["backend"],
        "ethernet-ram-result.json": json.dumps(bundle["ram"]),
        "ethernet-server-result.json": json.dumps(bundle["ram"]["server_result"]),
    }
    evidence = []
    for name, text in files.items():
        payload = text.encode("ascii")
        (bundle["directory"] / name).write_bytes(payload)
        evidence.append({"path": name, "sha256": hashlib.sha256(payload).hexdigest()})
    bundle["result"]["evidence"] = evidence
    save_result(bundle)


def verify(bundle):
    return handoff.verify_writer_result(bundle["directory"], direction=bundle["direction"], server_ipv4=SERVER)


@pytest.mark.parametrize("direction", ["promote", "rollback"])
def test_ram_gate_accepts_exact_f325_or_f321_and_scoped_server(direction):
    value = handoff.validate_ram_result(ram_result(direction), direction=direction, server_ipv4=SERVER)
    image, _ = handoff.exact_pair(direction)
    assert value["candidate_sha256"] == image["sha256"]
    assert value["bytes"] == image["bytes"]
    assert value["ram_crc32_observed"] == handoff.CRCS[image["sha256"]]
    assert value["transport"] == "ethernet-tftp" and value["server_closed"] is True


@pytest.mark.parametrize("bad", [
    "candidate_sha", "candidate_bytes", "candidate_crc", "ram_address", "server_bind",
    "server_client", "server_file_sha", "acked_bytes", "acked_blocks", "server_unclosed",
    "status_unknown", "server_wrong_subnet",
])
def test_ram_gate_rejects_wrong_image_crc_transfer_or_peer_scope(bad):
    ram = ram_result()
    server_ipv4 = SERVER
    if bad == "candidate_sha": ram["candidate_sha256"] = handoff.F321["sha256"]
    elif bad == "candidate_bytes": ram["candidate_bytes"] -= 1
    elif bad == "candidate_crc": ram["candidate_crc32"] = "00000000"
    elif bad == "ram_address": ram["address"] = "0x86000000"
    elif bad == "server_bind": ram["server_result"]["bind"] = "192.168.1.248"
    elif bad == "server_client": ram["server_result"]["allow_client"] = "192.168.1.1"
    elif bad == "server_file_sha": ram["server_result"]["file"]["sha256"] = handoff.F321["sha256"]
    elif bad == "acked_bytes": ram["server_result"]["counts"]["payload_bytes_acked"] -= 512
    elif bad == "acked_blocks": ram["server_result"]["counts"]["blocks_acked"] -= 1
    elif bad == "server_unclosed": ram["server_result"]["sockets_closed"] = False
    elif bad == "status_unknown": ram["status"] = "UNKNOWN"
    elif bad == "server_wrong_subnet":
        server_ipv4 = "192.168.2.249"
        ram["server_result"]["bind"] = server_ipv4
    with pytest.raises(ValueError):
        handoff.validate_ram_result(ram, direction="promote", server_ipv4=server_ipv4)


@pytest.mark.parametrize("direction", ["promote", "rollback"])
def test_writer_verifies_ethernet_evidence_with_unchanged_legacy_backend_label(tmp_path, direction):
    bundle = make_bundle(tmp_path, direction)
    result = verify(bundle)
    assert result["status"] == "PASS_VERIFIED_ETHERNET_WRITER"
    assert result["ram_load"]["transport"] == "ethernet-tftp"
    assert result["flash_control_transport"] == "uart-bootbase"
    assert "not bulk-transport evidence" in result["legacy_backend_transport_label"]
    assert result["full_slot_sha256_observed"] is None
    assert result["candidate_prefix_compared_bytes"] == bundle["image"]["bytes"]


@pytest.mark.parametrize("bad", ["hash", "foreign_path", "traversal", "duplicate_path", "fabricated_ymodem"])
def test_writer_rejects_unbound_or_fabricated_transport_evidence(tmp_path, bad):
    bundle = make_bundle(tmp_path)
    evidence = bundle["result"]["evidence"]
    if bad == "hash":
        (bundle["directory"] / "backend.log").write_text(bundle["backend"] + "changed\n", encoding="ascii")
    elif bad == "foreign_path":
        foreign = tmp_path / "foreign-backend.log"
        foreign.write_text(bundle["backend"], encoding="ascii")
        evidence[1]["path"] = str(foreign)
    elif bad == "traversal": evidence[1]["path"] = "../backend.log"
    elif bad == "duplicate_path": evidence[1]["path"] = evidence[0]["path"]
    elif bad == "fabricated_ymodem":
        for item, name in zip(evidence[2:], ("uart-ymodem-status.json", "uart-ymodem.log")):
            old_path = bundle["directory"] / item["path"]
            (bundle["directory"] / name).write_bytes(old_path.read_bytes())
            item["path"] = name
    save_result(bundle)
    with pytest.raises(ValueError): verify(bundle)


@pytest.mark.parametrize("bad", ["erase_offset", "erase_size", "write_offset", "write_size", "data_address", "duplicate", "out_of_order"])
def test_writer_rejects_wrong_duplicate_or_out_of_order_flash_commands(tmp_path, bad):
    bundle = make_bundle(tmp_path)
    lines = bundle["trace"].splitlines()
    if bad == "erase_offset": lines[0] = lines[0].replace("0x007e0000", "0x00040000")
    elif bad == "erase_size": lines[0] = lines[0].replace(f"0x{handoff.ERASE_BYTES:08x}", "0x005d0000")
    elif bad == "write_offset": lines[1] = lines[1].replace("0x007e0000", "0x00000000")
    elif bad == "write_size": lines[1] = lines[1].replace(f"0x{bundle['image']['bytes']:08x}", f"0x{bundle['image']['bytes']-1:08x}")
    elif bad == "data_address": lines[1] = lines[1].replace("0x83000000", "0x86000000")
    elif bad == "duplicate": lines.insert(1, lines[0])
    elif bad == "out_of_order": lines[0], lines[1] = lines[1], lines[0]
    bundle["trace"] = "\n".join(lines) + "\n"
    save_bundle(bundle)  # Correct file hashes do not make wrong commands acceptable.
    with pytest.raises(ValueError): verify(bundle)


@pytest.mark.parametrize("bad", ["result_pins", "status_unknown", "protected", "compare", "backend_markers", "forbidden_commands"])
def test_writer_requires_exact_result_and_physical_proof(tmp_path, bad):
    bundle = make_bundle(tmp_path)
    original = copy.deepcopy(bundle)
    variants = range(2) if bad in ("result_pins", "protected", "compare", "backend_markers", "forbidden_commands") else range(1)
    for variant in variants:
        bundle = copy.deepcopy(original)
        if bad == "result_pins":
            bundle["result"]["candidate_sha256" if variant == 0 else "backend_sha256"] = "0" * 64
        elif bad == "status_unknown": bundle["result"]["status"] = "UNKNOWN"
        elif bad == "protected":
            if variant == 0: bundle["result"]["protected_partitions"]["status"] = "UNKNOWN"
            else: bundle["backend"] = bundle["backend"].replace("PROTECTED_PARTITION_CRC_PASS=1", "PROTECTED_PARTITION_CRC_PASS=0")
        elif bad == "compare":
            if variant == 0: bundle["trace"] = bundle["trace"].replace(f"Total of {bundle['image']['bytes']}", "Total of 1")
            else: bundle["trace"] += f"Total of {bundle['image']['bytes']} bytes were the same\n"
        elif bad == "backend_markers":
            if variant == 0: bundle["backend"] = bundle["backend"].replace("OMF321_ERASED_PREFIX_CRC_PASS=1", "OMF321_ERASED_PREFIX_CRC_PASS=0")
            else: bundle["backend"] = "\n".join(reversed(bundle["backend"].splitlines())) + "\n"
        elif bad == "forbidden_commands":
            bundle["trace"] += "topaz>setenv serverip 192.168.1.249\n" if variant == 0 else "topaz>echo ready; saveenv\n"
        save_bundle(bundle)
        with pytest.raises(ValueError): verify(bundle)


def test_writer_rejects_same_directory_and_foreign_symlink_evidence_when_available(tmp_path):
    for placement in ("same", "foreign"):
        bundle = make_bundle(tmp_path / placement)
        target = (bundle["directory"] if placement == "same" else tmp_path) / f"{placement}-target.log"
        target.write_text(bundle["backend"], encoding="ascii")
        link = bundle["directory"] / "backend.log"
        link.unlink()  # Only this test's synthetic file.
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            pytest.skip("file symlink creation unavailable for this offline test")
        with pytest.raises(ValueError): verify(bundle)


class Callbacks:
    def __init__(self, bundle, *, failure=None, children=True):
        self.bundle = bundle
        self.failure = failure
        self.children = children
        self.trace = []
        self.writer_calls = []
        self.guards = 0

    def guard(self):
        self.trace.append("guard")
        self.guards += 1
        return not ((self.failure == "first_guard" and self.guards == 1)
                    or (self.failure == "second_guard" and self.guards == 2))

    def load_ram(self):
        self.trace.append("load_ram")
        value = copy.deepcopy(self.bundle["ram"])
        if self.failure == "ram": value["candidate_crc32"] = "00000000"
        return value

    def loader_closed(self):
        self.trace.append("loader_closed")
        return self.failure != "loader_closure"

    def writer(self, **kwargs):
        self.trace.append("writer")
        self.writer_calls.append(kwargs)
        if self.failure == "writer": raise RuntimeError("private callback detail must remain private")
        if self.failure == "evidence":
            self.bundle["result"]["status"] = "UNKNOWN"
            save_result(self.bundle)
        if self.failure == "ram_evidence_mismatch":
            self.bundle["ram"]["observation_id"] = "different-synthetic-transfer"
            save_bundle(self.bundle)
        return self.bundle["directory"]

    def all_children_stopped(self):
        self.trace.append("children")
        if self.children == "error": raise RuntimeError("synthetic child query failure")
        return self.children

    def run(self, network_authorized=True):
        return handoff.run_preloaded_handoff(
            direction=self.bundle["direction"], server_ipv4=SERVER, network_authorized=network_authorized,
            load_ram=self.load_ram, loader_closed=self.loader_closed, guard=self.guard,
            writer=self.writer, all_children_stopped=self.all_children_stopped,
        )


def assert_stopped(result, *, writer_started=False):
    assert result["status"] == "STOP_NO_AUTOMATIC_RETRY"
    assert result["writer_started"] is writer_started
    assert result["writer_verified"] is False
    assert result["automatic_recovery_started"] is False
    assert result["release_eligible"] is False


def test_handoff_missing_network_authority_invokes_no_callback(tmp_path):
    for authorization in (False, None, 1, "true"):
        callbacks = Callbacks(make_bundle(tmp_path / str(authorization)))
        result = callbacks.run(network_authorized=authorization)
        assert_stopped(result)
        assert callbacks.trace == [] and callbacks.writer_calls == []


def test_handoff_first_guard_failure_checks_children_and_retains_uncertain_lease(tmp_path):
    callbacks = Callbacks(make_bundle(tmp_path), failure="first_guard", children=False)
    result = callbacks.run()
    assert_stopped(result)
    assert callbacks.trace == ["guard", "children"]
    assert result["retain_lease_required"] is True


def test_handoff_second_guard_failure_cannot_start_writer(tmp_path):
    callbacks = Callbacks(make_bundle(tmp_path), failure="second_guard")
    result = callbacks.run()
    assert_stopped(result)
    assert callbacks.trace == ["guard", "load_ram", "loader_closed", "guard", "children"]
    assert callbacks.writer_calls == []


def test_handoff_wrong_ram_crc_cannot_start_writer(tmp_path):
    callbacks = Callbacks(make_bundle(tmp_path), failure="ram")
    result = callbacks.run()
    assert_stopped(result)
    assert callbacks.trace == ["guard", "load_ram", "children"]
    assert callbacks.writer_calls == []


def test_handoff_unproved_loader_closure_cannot_start_writer(tmp_path):
    callbacks = Callbacks(make_bundle(tmp_path), failure="loader_closure")
    result = callbacks.run()
    assert_stopped(result)
    assert callbacks.trace == ["guard", "load_ram", "loader_closed", "children"]
    assert callbacks.writer_calls == []


def test_handoff_calls_preloaded_writer_once_and_uses_real_fixture_verifier(tmp_path):
    callbacks = Callbacks(make_bundle(tmp_path))
    result = callbacks.run()
    assert result["status"] == "PASS_ETHERNET_RAM_TO_WRITER_HANDOFF"
    assert result["writer_verified"] is True and result["containment_verified"] is True
    assert result["retain_lease_required"] is False and result["automatic_recovery_started"] is False
    assert result["physical_adapters_qualified_by_this_module"] is False
    assert callbacks.trace == ["guard", "load_ram", "loader_closed", "guard", "writer", "children"]
    assert len(callbacks.writer_calls) == 1
    call = callbacks.writer_calls[0]
    assert call["image"]["sha256"] == handoff.F325["sha256"]
    assert call["current"]["sha256"] == handoff.F321["sha256"]
    assert call["skip_reboot"] is True and call["skip_network_transfer"] is True
    assert result["writer"]["ram_load"]["transport"] == "ethernet-tftp"


@pytest.mark.parametrize("failure", ["writer", "evidence"])
def test_handoff_writer_or_evidence_failure_never_retries_or_recovers(tmp_path, failure):
    callbacks = Callbacks(make_bundle(tmp_path), failure=failure)
    result = callbacks.run()
    assert_stopped(result, writer_started=True)
    assert len(callbacks.writer_calls) == 1 and callbacks.trace[-1] == "children"
    assert "private callback detail" not in json.dumps(result)


def test_handoff_rejects_different_ram_result_even_with_valid_writer_hashes(tmp_path):
    bundle = make_bundle(tmp_path)
    original_ram = copy.deepcopy(bundle["ram"])
    callbacks = Callbacks(bundle, failure="ram_evidence_mismatch")
    result = callbacks.run()
    assert_stopped(result, writer_started=True)
    assert len(callbacks.writer_calls) == 1
    # The replacement is otherwise a complete, correctly hashed evidence set.
    assert verify(bundle)["status"] == "PASS_VERIFIED_ETHERNET_WRITER"
    with pytest.raises(ValueError):
        handoff.verify_writer_result(bundle["directory"], direction="promote", server_ipv4=SERVER,
                                     expected_ram_result=original_ram)


@pytest.mark.parametrize("children", [False, "error"])
def test_handoff_unproved_child_termination_retains_lease_even_after_verified_write(tmp_path, children):
    callbacks = Callbacks(make_bundle(tmp_path), children=children)
    result = callbacks.run()
    assert_stopped(result, writer_started=True)
    assert result["retain_lease_required"] is True and result["containment_verified"] is False
    assert len(callbacks.writer_calls) == 1
