"""Only synthetic JSON/logs and injected processes; no device or image access."""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import f323_ethernet_load_cli as loader
import f323_ethernet_writer as writer
import f323_execution_contract as original
from f323_ethernet_ram_gate import _COUNTERS


SERVER = "192.168.1.249"
SECRET = "SYNTHETIC-CONTEXT-OR-EXCEPTION-DO-NOT-LOG"


def make_plan(direction="promote"):
    image, current = writer.handoff.exact_pair(direction)
    protected_sha = {f"mtd{part}": str(part) * 64 for part in (0, 1, 2, 3, 5)}
    protected_crc = {f"mtd{part}": f"{part:08x}" for part in (0, 1, 2, 3, 5)}
    protected_crc["mtd3"] = "f7d14d3d"  # Protected mtd3, never the F314 image CRC.
    preflight = {"mode": "dry-run", "candidate_sha256": image["sha256"], "candidate_bytes": image["bytes"],
                 "candidate_crc32": writer.handoff.CRCS[image["sha256"]], "current_live_sha256": current["full_slot_sha256"],
                 "current_live_crc32": current["full_slot_crc32"], "expected_full_slot_sha256": image["full_slot_sha256"],
                 "expected_full_slot_crc32": image["full_slot_crc32"], "target_bytes": writer.handoff.SLOT_BYTES,
                 "target_offset": "0x007e0000", "layout_mode": "squashfs-split",
                 "protected_partition_sha256": protected_sha, "protected_partition_crc32": protected_crc,
                 "rollback_sha256": protected_sha["mtd3"], "rollback_crc32": protected_crc["mtd3"]}
    return {"schema": writer.PLAN_SCHEMA, "direction": direction, "transport": "ethernet-tftp",
            "image": copy.deepcopy(image), "current": copy.deepcopy(current),
            "erase_bytes": writer.handoff.ERASE_BYTES, "slot_bytes": writer.handoff.SLOT_BYTES,
            "executor_review_verified": True, "network_authorization_verified": True,
            "network": {"server_ipv4": SERVER, "client_ipv4": "192.168.1.90", "interface_index": 15, "interface_alias": "Ethernet"},
            "preflight": preflight, "protected_baseline_sha256": protected_sha, "protected_baseline_crc32": protected_crc,
            "environment": original.environment(image, current)}


def native_fixture(plan):
    image = plan["image"]
    blocks = image["bytes"] // 512 + 1
    counts = dict.fromkeys(_COUNTERS, 0)
    counts.update(listener_datagrams_received=1, transfer_datagrams_received=blocks, data_packets_sent=blocks,
                  blocks_acked=blocks, data_bytes_sent_including_retries=image["bytes"], payload_bytes_acked=image["bytes"])
    server = {"schema": "openmitrastar.f323-scoped-tftp/v1", "status": "PASS_TFTP_SINGLE_TRANSFER", "reason": None,
              "bind": SERVER, "port": 69, "allow_client": "192.168.1.90", "allow_file": image["base"] + ".webformat.bin",
              "file": {"path": str(Path(image["directory"]) / (image["base"] + ".webformat.bin")),
                       "sha256": image["sha256"], "bytes": image["bytes"], "blocks_including_terminal": blocks},
              "timeout_seconds": 300, "ack_timeout_seconds": 0.5, "max_retries": 5, "elapsed_seconds": 1.0,
              "transfer_started": True, "transfer_complete": True, "sockets_closed": True,
              "raw_content_logged": False, "rejected_filenames_logged": False, "flash": False, "boot_verified": False,
              "client_tid": 12345, "transfer_tid": 54321, "counts": counts}
    ram = {"schema": writer.handoff.RAM_SCHEMA, "status": "PASS_ETHERNET_RAM_GATE", "candidate_sha256": image["sha256"],
           "candidate_bytes": image["bytes"], "candidate_crc32": writer.handoff.CRCS[image["sha256"]],
           "address": "0x83000000", "server_closed": True, "flash_writes": 0, "environment_saved": False,
           "runtime_adapters_verified": False, "tx_commands_issued": 8, "tftp_commands_issued": 1,
           "checks": dict.fromkeys(("volatile_network_environment", "server_ready", "decimal_and_hex_transfer_count",
                                    "scoped_server_transfer", "filesize", "iminfo", "ram_crc32"), True),
           "server_result": server}
    return {"schema": writer.NATIVE_SCHEMA, "status": "PASS_NATIVE_ETHERNET_RAM_LOAD",
            "candidate_sha256": image["sha256"], "candidate_bytes": image["bytes"], "target_host": "192.168.1.90",
            "server_ipv4": SERVER, "writer_ready": False, "ram_handoff_ready": True, "retain_lease_required": False,
            "flash_written": False, "rebooted": False, "host_network_or_firewall_changed": False,
            "loader_process_exit_observed_by_parent": False, "parent_execution_review_verified": True,
            "raw_uart_or_guard_output_logged": False, "ram_result": ram,
            "cleanup": {"server": True, "uart": True, "guard_helpers": True}, "native_cleanup_verified": True}


def save_native(directory, native):
    for name, value in ((writer.NATIVE_FILE, native), (writer.RAM_FILE, native["ram_result"]),
                        (writer.SERVER_FILE, native["ram_result"]["server_result"])):
        (directory / name).write_text(json.dumps(value), encoding="ascii")


def bind_receipt(directory, plan, environ):
    native_path = directory / writer.NATIVE_FILE
    environ[writer.PRELOADED_ENV] = json.dumps({"schema": writer.PRELOADED_SCHEMA, "direction": plan["direction"],
        "candidate_sha256": plan["image"]["sha256"], "native_result_path": str(native_path),
        "native_result_sha256": writer.digest(native_path.read_bytes()),
        "physical_context_sha256": writer.digest(environ[writer.CONTEXT_ENV].encode("utf-8")), "loader_job_closed": True})


class FakeProcess:
    def __init__(self):
        self.code = 0
        self.timeout = False
        self.refuse_stop = False
        self.waits = []
        self.terminated = self.killed = 0

    def poll(self):
        return self.code

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.timeout and self.code is None:
            raise subprocess.TimeoutExpired("synthetic", timeout)
        return self.code

    def terminate(self):
        self.terminated += 1
        if not self.refuse_stop:
            self.code = -15

    def kill(self):
        self.killed += 1
        if not self.refuse_stop:
            self.code = -9


class FakeBackend:
    def __init__(self, plan):
        self.plan = plan
        self.process = FakeProcess()
        self.calls = []
        self.bad_proof = False
        self.raise_spawn = False

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.raise_spawn:
            raise RuntimeError(SECRET)
        image, current, pre = self.plan["image"], self.plan["current"], self.plan["preflight"]
        trace = (f"topaz>spi_flash erase 0x007e0000 0x{writer.handoff.ERASE_BYTES:08x}\n"
                 f"topaz>spi_flash write 0x007e0000 0x83000000 0x{image['bytes']:08x}\n"
                 f"Total of {image['bytes']} bytes were the same\n")
        text = (f"MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc={pre['rollback_crc32']} current_live_crc={current['full_slot_crc32']}\n"
                "OMF321_ERASED_PREFIX_CRC_PASS=1 bytes=6160384 crc=aa86bf2e\n"
                "PROTECTED_PARTITION_CRC_PASS=1\n"
                f"MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc={image['full_slot_crc32']} prefix=identical\n"
                f"MTD4_FLASH_AND_READBACK_PASS=1 candidate={image['sha256']} candidate_transport=uart-ymodem\n")
        if self.bad_proof:
            trace += "topaz>saveenv\n"
        Path(command[command.index("-Transcript") + 1]).write_text(trace, encoding="ascii")
        kwargs["stdout"].write(text.encode("ascii"))
        return self.process


@pytest.fixture
def rig(tmp_path):
    plan = make_plan()
    directory = tmp_path / "attempt"
    directory.mkdir()
    native = native_fixture(plan)
    save_native(directory, native)
    environ = {writer.CONTEXT_ENV: SECRET, "OM_Q3_FLASH_STALE_OVERRIDE": "remove"}
    bind_receipt(directory, plan, environ)
    guard = Mock(return_value=True)
    guard.close_all.return_value = True
    factory = Mock(return_value=guard)
    backend = FakeBackend(plan)
    kwargs = dict(ack=plan["image"]["ack"], timeout=900, environ=environ, guard_factory=factory,
                  popen_factory=backend, resolve_program=lambda _: str(tmp_path / "pwsh.exe"))
    return SimpleNamespace(plan=plan, directory=directory, native=native, environ=environ,
                           guard=guard, factory=factory, backend=backend, kwargs=kwargs)


def run(rig):
    return writer.execute_writer(rig.plan, rig.directory, **rig.kwargs)


def test_complete_preloaded_writer_uses_original_verifier_and_exact_backend_arguments(rig):
    original_ram = (rig.directory / writer.RAM_FILE).read_bytes()
    result = run(rig)
    assert result["status"] == "PASS" and result["backend_process_exited"] is True
    assert result["guard_helpers_closed"] is True and result["retain_lease_required"] is False
    assert writer.handoff.verify_writer_result(rig.directory, direction="promote", server_ipv4=SERVER)["status"] == "PASS_VERIFIED_ETHERNET_WRITER"
    command, options = rig.backend.calls[0]
    assert command[command.index("-File") + 1] == str(writer.BACKEND)
    assert command.count("-SkipReboot") == command.count("-SkipNetworkTransfer") == 1
    assert "-SkipBootbasePing" not in command and "-RequireProductReady" not in command
    assert command[command.index("-RollbackCrc32") + 1] == "f7d14d3d"
    assert command[command.index("-CurrentLiveCrc32") + 1] == rig.plan["current"]["full_slot_crc32"]
    assert command[command.index("-EraseBytes") + 1] == str(0x5e0000)
    assert command[command.index("-Candidate") + 1] == rig.plan["environment"]["OM_Q3_FLASH_CANDIDATE"]
    assert options["env"][writer.CONTEXT_ENV] == SECRET and "OM_Q3_FLASH_STALE_OVERRIDE" not in options["env"]
    assert options["stdin"] == subprocess.DEVNULL and options["stderr"] == subprocess.STDOUT
    assert options["stdout"] != subprocess.PIPE and options["shell"] is False
    assert 1200 in rig.backend.process.waits
    assert (rig.directory / writer.RAM_FILE).read_bytes() == original_ram
    assert not (rig.directory / "tftp.log").exists() and not (rig.directory / "uart-ymodem.log").exists()
    assert result["readback"]["full_slot_sha256_observed"] is None
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("executor_review_verified", False), ("network_authorization_verified", 1)])
def test_unqualified_plan_has_no_guard_backend_or_evidence_writes(rig, field, value):
    rig.plan[field] = value
    result = run(rig)
    assert result["status"] != "PASS" and rig.backend.calls == []
    rig.factory.assert_not_called()
    assert not (rig.directory / "result.json").exists()


@pytest.mark.parametrize("kind", ["ack", "timeout", "missing_receipt", "context", "hash", "closure", "path"])
def test_ack_or_preloaded_binding_failure_cannot_open_backend(rig, kind, tmp_path):
    if kind == "ack":
        rig.kwargs["ack"] = "old-ACK"
    elif kind == "timeout":
        rig.kwargs["timeout"] = 599
    elif kind == "missing_receipt":
        rig.environ.pop(writer.PRELOADED_ENV)
    elif kind == "context":
        rig.environ[writer.CONTEXT_ENV] += "changed"
    else:
        receipt = json.loads(rig.environ[writer.PRELOADED_ENV])
        if kind == "hash":
            receipt["native_result_sha256"] = "0" * 64
        elif kind == "closure":
            receipt["loader_job_closed"] = 1
        else:
            other = tmp_path / writer.NATIVE_FILE
            other.write_bytes((rig.directory / writer.NATIVE_FILE).read_bytes())
            receipt["native_result_path"] = str(other)
        rig.environ[writer.PRELOADED_ENV] = json.dumps(receipt)
    result = run(rig)
    assert result["status"] != "PASS" and rig.backend.calls == []
    rig.factory.assert_not_called()


@pytest.mark.parametrize("kind", ["native_status", "native_writer_ready", "native_cleanup", "ram_crc", "ram_checks",
                                  "server_path", "server_count", "server_raw", "server_cleanup"])
def test_semantic_native_ram_and_server_failures_rejected_even_after_outer_rehash(rig, kind):
    if kind == "native_status":
        rig.native["status"] = "STOP_NO_AUTOMATIC_RETRY"
    elif kind == "native_writer_ready":
        rig.native["writer_ready"] = True
    elif kind == "native_cleanup":
        rig.native["cleanup"]["uart"] = False
    elif kind == "ram_crc":
        rig.native["ram_result"]["candidate_crc32"] = "00000000"
    elif kind == "ram_checks":
        rig.native["ram_result"]["checks"]["iminfo"] = 1
    else:
        server = rig.native["ram_result"]["server_result"]
        if kind == "server_path":
            server["file"]["path"] = "foreign.bin"
        elif kind == "server_count":
            server["counts"]["blocks_acked"] -= 1
        elif kind == "server_raw":
            server["raw_packet"] = SECRET
        else:
            server["sockets_closed"] = False
    save_native(rig.directory, rig.native)
    bind_receipt(rig.directory, rig.plan, rig.environ)
    assert run(rig)["status"] != "PASS"
    assert rig.backend.calls == []
    rig.factory.assert_not_called()


def test_guard_refusal_is_cleaned_up_and_cannot_launch_writer(rig):
    rig.guard.return_value = False
    result = run(rig)
    assert result["status"] != "PASS" and rig.backend.calls == []
    rig.guard.close_all.assert_called_once()


def test_context_change_during_guard_cannot_cross_the_backend_boundary(rig):
    def change():
        rig.environ[writer.CONTEXT_ENV] += "changed"
        return True
    rig.guard.side_effect = change
    assert run(rig)["status"] != "PASS" and rig.backend.calls == []


@pytest.mark.parametrize("kind", ["nonzero", "timeout", "unknown_spawn", "uncontained", "guard_close", "bad_proof"])
def test_backend_or_proof_failure_never_retries_or_publishes_pass(rig, kind):
    if kind == "nonzero":
        rig.backend.process.code = 1
    elif kind in {"timeout", "uncontained"}:
        rig.backend.process.code = None
        rig.backend.process.timeout = True
        rig.backend.process.refuse_stop = kind == "uncontained"
    elif kind == "unknown_spawn":
        rig.backend.raise_spawn = True
    elif kind == "guard_close":
        rig.guard.close_all.return_value = False
    else:
        rig.backend.bad_proof = True
    result = run(rig)
    assert result["status"] == "STOP_NO_AUTOMATIC_RETRY" and len(rig.backend.calls) == 1
    assert result["automatic_retry"] is False and result["automatic_rollback"] is False
    assert json.loads((rig.directory / "result.json").read_text())["status"] != "PASS"
    assert result["retain_lease_required"] is (kind in {"unknown_spawn", "uncontained", "guard_close"})
    assert SECRET not in json.dumps(result)


def test_existing_writer_files_are_preserved_and_block_new_backend(rig):
    marker = rig.directory / "backend.log"
    marker.write_text("existing", encoding="ascii")
    assert run(rig)["status"] != "PASS" and marker.read_text() == "existing"
    assert rig.backend.calls == []


def test_metadata_only_rollback_command_uses_exact_f321_and_current_f323(tmp_path):
    plan = make_plan("rollback")
    writer.validate_plan(plan, execute=True)
    command = writer.backend_command(plan, tmp_path, timeout=900, program=str(tmp_path / "pwsh.exe"))
    assert command[command.index("-Ack") + 1] == plan["image"]["ack"]
    assert command[command.index("-CurrentLiveCrc32") + 1] == "ba8a6167"
    assert command[command.index("-ExpectedCandidateCrc32") + 1] == "bd1135df"


@pytest.mark.parametrize("entry,flag", [(writer, "--evidence-dir"), (loader, "--output-dir")])
def test_both_cli_defaults_are_real_dry_paths_over_fixture_contract_without_callbacks(rig, entry, flag, tmp_path):
    plan = copy.deepcopy(rig.plan)
    plan.update(executor_review_verified=False, network_authorization_verified=False)
    contract = SimpleNamespace(plan=Mock(return_value=plan))
    callback = Mock(side_effect=AssertionError("physical callback forbidden"))
    options = {"writer" if entry is writer else "loader": callback}
    with redirect_stdout(io.StringIO()) as output:
        assert entry.main([flag, str(tmp_path / "unused")], contract=contract, **options) == 0
    result = json.loads(output.getvalue())
    assert result["status"] == "DRY_RUN" and result["hardware_actions_performed"] is False
    callback.assert_not_called()
    assert not (tmp_path / "unused").exists()


def test_loader_execute_rechecks_context_and_persisted_native_files(rig, tmp_path):
    output = tmp_path / "new-loader"
    guard = Mock(return_value=True)
    guard.close_all.return_value = True
    factory = Mock(return_value=guard)

    def fake_native(**kwargs):
        assert kwargs == {"direction": "promote", "server_ipv4": SERVER, "output_dir": output,
                          "execute": True, "network_authorized": True, "parent_review_verified": True}
        output.mkdir()
        save_native(output, rig.native)
        return rig.native

    result = loader.execute_loader(rig.plan, output, native_loader=fake_native, guard_factory=factory, environ=rig.environ)
    assert result["status"] == "PASS_NATIVE_ETHERNET_RAM_LOAD" and result["ram_handoff_ready"] is True
    assert result["writer_ready"] is False and result["native_cleanup_verified"] is True
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("kind", ["authority", "guard", "native_missing_file", "native_uncertain", "final_guard_cleanup"])
def test_loader_failures_never_grant_writer_readiness_and_preserve_uncertainty(rig, tmp_path, kind):
    output = tmp_path / "new-loader"
    guard = Mock(return_value=kind != "guard")
    guard.close_all.side_effect = [True, False] if kind == "final_guard_cleanup" else None
    guard.close_all.return_value = True
    factory = Mock(return_value=guard)
    native = copy.deepcopy(rig.native)
    if kind == "authority":
        rig.plan["network_authorization_verified"] = False
    elif kind == "native_uncertain":
        native.update(status="STOP_NO_AUTOMATIC_RETRY", native_cleanup_verified=False, retain_lease_required=True)

    def fake_native(**kwargs):
        if kind != "native_missing_file":
            output.mkdir()
            save_native(output, native)
        return native

    result = loader.execute_loader(rig.plan, output, native_loader=fake_native, guard_factory=factory, environ=rig.environ)
    assert result["status"] != "PASS_NATIVE_ETHERNET_RAM_LOAD" and result["writer_ready"] is False
    assert result["ram_handoff_ready"] is False
    assert result["retain_lease_required"] is (kind in {"native_uncertain", "final_guard_cleanup"})
    if kind == "authority":
        factory.assert_not_called()
