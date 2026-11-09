"""Mocked lifecycle plus one loopback fixture; never accesses HGW or firmware."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
from unittest.mock import Mock

import pytest

import f325_ethernet_server_process as adapter
from f325_scoped_tftp import EVENT_SCHEMA, RESULT_SCHEMA, VerifiedPayload, block_count
from f325_ethernet_ram_gate import _COUNTERS


BIND, CLIENT = "192.168.1.35", "192.168.1.90"  # Mock strings; never bound by these tests.
SENTINEL = "UNTRUSTED-STDERR-OR-PACKET-DO-NOT-ECHO"


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.on_sleep = None

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.on_sleep:
            self.on_sleep()


class FakeChild:
    def __init__(self, clock):
        self.clock = clock
        self.code = None
        self.terminate_calls = self.kill_calls = 0
        self.wait_calls = []
        self.terminate_exits = self.kill_exits = True
        self.poll_error = self.terminate_error = None
        self.wait_value = None

    def poll(self):
        if self.poll_error:
            raise self.poll_error
        return self.code

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        if self.wait_value is not None:
            return self.wait_value
        if self.code is None:
            self.clock.now += timeout
            raise subprocess.TimeoutExpired("synthetic-child", timeout)
        return self.code

    def terminate(self):
        self.terminate_calls += 1
        if self.terminate_error:
            raise self.terminate_error
        if self.terminate_exits:
            self.code = -15

    def kill(self):
        self.kill_calls += 1
        if self.kill_exits:
            self.code = -9


class FakeLaunch:
    def __init__(self, payload, clock):
        self.payload, self.clock = payload, clock
        self.calls = []
        self.child = FakeChild(clock)
        self.ready_override = None
        self.raw_start = None
        self.ready = {"schema": EVENT_SCHEMA, "event": "ready", "bind": BIND, "port": 69,
                      "allow_client": CLIENT, "allow_file": payload.source_path.name,
                      "file": payload.metadata(), "timeout_seconds": 300}
        blocks = block_count(payload.expected_bytes)
        counts = dict.fromkeys(_COUNTERS, 0)
        counts.update(listener_datagrams_received=1, transfer_datagrams_received=blocks,
                      data_packets_sent=blocks, data_bytes_sent_including_retries=payload.expected_bytes,
                      blocks_acked=blocks, payload_bytes_acked=payload.expected_bytes)
        self.result = {"schema": RESULT_SCHEMA, "status": "PASS_TFTP_SINGLE_TRANSFER", "reason": None,
                       "bind": BIND, "port": 69, "allow_client": CLIENT, "allow_file": payload.source_path.name,
                       "file": payload.metadata(), "timeout_seconds": 300, "ack_timeout_seconds": 0.5,
                       "max_retries": 5, "transfer_started": True, "transfer_complete": True,
                       "counts": counts, "raw_content_logged": False, "rejected_filenames_logged": False,
                       "flash": False, "boot_verified": False, "sockets_closed": True,
                       "client_tid": 12345, "transfer_tid": 54321, "elapsed_seconds": 0.1,
                       "mode": "execute", "network_access": True, "script_sha256": adapter.SERVER_SHA256}

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        self.stdout, self.stderr = kwargs["stdout"], kwargs["stderr"]
        self.output = Path(args[args.index("--output-dir") + 1])
        row = self.ready_override or self.ready
        self.stdout.write(self.raw_start if self.raw_start is not None else json.dumps(row).encode("ascii") + b"\n")
        return self.child

    def complete(self, *, exit_code=0, eof=True, duplicate_result=False, result_override=None):
        self.output.mkdir()
        result = copy.deepcopy(result_override or self.result)
        start = {"schema": EVENT_SCHEMA, "event": "transfer_started", "client": CLIENT,
                 "client_tid": 12345, "transfer_tid": 54321, "file": self.payload.metadata()}
        end = {"schema": EVENT_SCHEMA, "event": "complete", "result": result}
        self.stdout.write(json.dumps(start).encode("ascii") + b"\n")
        self.stdout.write(json.dumps(end).encode("ascii") + (b"\n" if eof else b""))
        text = json.dumps(result)
        if duplicate_result:
            text += text
        (self.output / "result.json").write_text(text, encoding="ascii")
        self.child.code = exit_code


@pytest.fixture
def rig(tmp_path):
    data = b"synthetic data" * 50
    source = tmp_path / "fixture.bin"
    source.write_bytes(data)
    payload = VerifiedPayload(source, hashlib.sha256(data).hexdigest(), len(data), data)
    clock = FakeClock()
    launch = FakeLaunch(payload, clock)
    guard = Mock(return_value=True)
    service = adapter.ScopedTftpProcess(guard=guard, output_dir=tmp_path / "adapter",
                                       popen_factory=launch, clock=clock, sleep=clock.sleep)
    return service, payload, launch, guard, clock


def start(service, payload):
    return service.start(payload, bind=BIND, client=CLIENT, filename=payload.source_path.name)


def test_constructor_has_no_files_process_or_guard_effects(rig):
    service, _, launch, guard, _ = rig
    assert not service.output_dir.exists() and launch.calls == []
    guard.assert_not_called()


@pytest.mark.parametrize("value", [False, None, 1, RuntimeError(SENTINEL)])
def test_guard_failure_prevents_reads_directories_and_launch(rig, value):
    service, payload, launch, guard, _ = rig
    service.server_source = Path("must-never-be-read.py")
    if isinstance(value, Exception):
        guard.side_effect = value
    else:
        guard.return_value = value
    with pytest.raises(adapter.ServerProcessFailure) as error:
        start(service, payload)
    assert SENTINEL not in str(error.value)
    assert not service.output_dir.exists() and launch.calls == []


def test_source_hash_failure_cannot_launch_or_create_output(rig, tmp_path):
    service, payload, launch, _, _ = rig
    bad = tmp_path / "wrong.py"
    bad.write_text("raise RuntimeError('fixture')", encoding="ascii")
    service.server_source = bad
    with pytest.raises(adapter.ServerProcessFailure, match="server_source_hash"):
        start(service, payload)
    assert launch.calls == [] and not service.output_dir.exists()


def test_launch_uses_exact_new_snapshot_no_firmware_copy_no_pipe_or_breakaway(rig):
    service, payload, launch, guard, _ = rig
    ready = start(service, payload)
    args, kwargs = launch.calls[0]
    snapshot = Path(args[3])
    assert args[:3] == [sys.executable, "-I", "-B"]
    assert snapshot.parent == service.output_dir
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == adapter.SERVER_SHA256
    assert args[args.index("--file") + 1] == str(payload.source_path)
    assert args[args.index("--expected-sha256") + 1] == payload.expected_sha256
    assert kwargs["stdout"] != subprocess.PIPE and kwargs["stderr"] != subprocess.PIPE
    assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["shell"] is False
    assert kwargs["close_fds"] is True
    expected_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    assert kwargs["creationflags"] == expected_flags
    assert kwargs["creationflags"] & getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000) == 0
    assert not (service.output_dir / payload.source_path.name).exists()
    assert ready["file"] == payload.metadata() and guard.call_count == 2
    assert service.close() is True


def test_source_edit_after_snapshot_does_not_change_the_executed_copy(rig, tmp_path):
    service, payload, launch, _, _ = rig
    source_copy = tmp_path / "mutable-server-source.py"
    source_copy.write_bytes(adapter.SERVER_SOURCE.read_bytes())
    service.server_source = source_copy

    def mutate_original_before_launch(args, **kwargs):
        source_copy.write_text("raise RuntimeError('not executed')", encoding="ascii")
        snapshot = Path(args[3])
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == adapter.SERVER_SHA256
        assert snapshot != source_copy
        return launch(args, **kwargs)

    service._popen = mutate_original_before_launch
    start(service, payload)
    assert hashlib.sha256(source_copy.read_bytes()).hexdigest() != adapter.SERVER_SHA256
    assert service.close() is True


def test_eof_reader_refuses_non_regular_paths_before_open(tmp_path):
    with pytest.raises(adapter.ServerProcessFailure, match="regular_file_required"):
        adapter._bounded_read(tmp_path, 100)


@pytest.mark.parametrize("field,value", [("bind", "192.168.1.36"), ("port", 70), ("port", True),
                                         ("allow_client", "192.168.1.1"), ("event", "complete"),
                                         ("timeout_seconds", 301)])
def test_wrong_ready_is_rejected_and_child_is_contained(rig, field, value):
    service, payload, launch, _, _ = rig
    launch.ready_override = {**launch.ready, field: value}
    with pytest.raises(adapter.ServerProcessFailure):
        start(service, payload)
    assert launch.child.terminate_calls == 1 and launch.child.code == -15
    assert all(handle.closed for handle in (launch.stdout, launch.stderr))


def test_partial_ready_is_waited_for_without_blocking_or_early_acceptance(rig):
    service, payload, launch, _, clock = rig
    complete = json.dumps(launch.ready).encode("ascii") + b"\n"
    launch.raw_start = complete[:15]

    def append_once():
        launch.stdout.write(complete[15:])
        clock.on_sleep = None

    clock.on_sleep = append_once
    ready = start(service, payload)
    assert ready["event"] == "ready" and clock.now == pytest.approx(0.05)
    assert service.close() is True


@pytest.mark.parametrize("fragment", [b"", b'{"schema":', b'{"schema":broken}\n'])
def test_missing_partial_or_malformed_ready_is_bounded_and_never_logged_in_error(rig, fragment):
    service, payload, launch, _, clock = rig
    launch.raw_start = fragment
    with pytest.raises(adapter.ServerProcessFailure):
        start(service, payload)
    assert clock.now <= 15
    assert launch.child.code == -15 and launch.stdout.closed and launch.stderr.closed


def test_start_cannot_be_repeated_even_after_guard_failure(rig):
    service, payload, launch, guard, _ = rig
    guard.return_value = False
    with pytest.raises(adapter.ServerProcessFailure):
        start(service, payload)
    guard.return_value = True
    with pytest.raises(adapter.ServerProcessFailure, match="start_is_one_shot"):
        start(service, payload)
    assert launch.calls == []


def test_existing_directory_is_never_reused(rig):
    service, payload, launch, _, _ = rig
    service.output_dir.mkdir()
    with pytest.raises(adapter.ServerProcessFailure):
        start(service, payload)
    assert launch.calls == [] and list(service.output_dir.iterdir()) == []


def test_finish_requires_rc_zero_unique_complete_result_and_bound_server_hash(rig):
    service, payload, launch, _, _ = rig
    start(service, payload)
    launch.result["raw_payload"] = SENTINEL
    launch.result["file"]["private_extra"] = SENTINEL
    launch.complete()
    result = service.finish()
    assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER" and result["sockets_closed"] is True
    assert SENTINEL not in str(result)
    assert "script_sha256" not in result and result["file"] == payload.metadata()
    assert service.close() is True and launch.child.terminate_calls == 0
    assert launch.stdout.closed and launch.stderr.closed


def test_fake_pass_file_cannot_override_a_live_child_handle(rig):
    service, payload, launch, _, _ = rig
    start(service, payload)
    launch.complete()
    launch.child.code = None  # A forged PASS document while the owned process lives.
    with pytest.raises(adapter.ServerProcessFailure, match="child_still_running"):
        service.finish(timeout=0.1)
    assert launch.child.terminate_calls == 1


@pytest.mark.parametrize("kind", ["rc", "hash", "status", "partial_eof", "duplicate_json", "stderr", "count", "size"])
def test_finish_rejects_failed_or_ambiguous_terminal_evidence(rig, kind):
    service, payload, launch, _, _ = rig
    start(service, payload)
    if kind == "hash":
        launch.result["script_sha256"] = "0" * 64
    elif kind == "status":
        launch.result["status"] = "FAIL_TFTP_SINGLE_TRANSFER"
    elif kind == "count":
        launch.result["counts"]["blocks_acked"] -= 1
    elif kind == "size":
        launch.result["file"]["bytes"] += 1
    elif kind == "stderr":
        launch.stderr.write(SENTINEL.encode("ascii"))
    launch.complete(exit_code=1 if kind == "rc" else 0, eof=kind != "partial_eof", duplicate_result=kind == "duplicate_json")
    with pytest.raises(adapter.ServerProcessFailure) as error:
        service.finish()
    assert SENTINEL not in str(error.value)
    assert launch.stdout.closed and launch.stderr.closed


def test_pass_file_without_terminal_stdout_sequence_is_not_accepted(rig):
    service, payload, launch, _, _ = rig
    start(service, payload)
    launch.output.mkdir()
    (launch.output / "result.json").write_text(json.dumps(launch.result), encoding="ascii")
    launch.child.code = 0
    with pytest.raises(adapter.ServerProcessFailure, match="terminal_event_sequence"):
        service.finish()


def test_close_escalates_only_the_owned_handle_then_proves_exit(rig):
    service, payload, launch, _, _ = rig
    start(service, payload)
    launch.child.terminate_exits = False
    assert service.close() is True
    assert launch.child.terminate_calls == launch.child.kill_calls == 1
    assert launch.child.code == -9 and launch.stdout.closed and launch.stderr.closed


@pytest.mark.parametrize("kind", ["still_alive", "poll_error", "terminate_error", "false_exit_value"])
def test_uncertain_close_returns_false_but_always_closes_log_handles(rig, kind):
    service, payload, launch, _, _ = rig
    start(service, payload)
    if kind == "still_alive":
        launch.child.terminate_exits = launch.child.kill_exits = False
    elif kind == "poll_error":
        launch.child.poll_error = RuntimeError(SENTINEL)
    elif kind == "terminate_error":
        launch.child.terminate_error = RuntimeError(SENTINEL)
    else:
        launch.child.code = 0
        launch.child.wait_value = False
    assert service.close() is False
    assert launch.stdout.closed and launch.stderr.closed


def test_test_mode_never_accepts_a_non_loopback_endpoint(rig, tmp_path):
    _, payload, launch, guard, clock = rig
    service = adapter.ScopedTftpProcess(guard=guard, output_dir=tmp_path / "test-adapter", test_mode=True, port=0,
                                       popen_factory=launch, clock=clock, sleep=clock.sleep)
    with pytest.raises(adapter.ServerProcessFailure):
        service.start(payload, bind="127.0.0.1", client=CLIENT, filename=payload.source_path.name, timeout=1)
    assert launch.calls == [] and not service.output_dir.exists()


def test_complete_real_child_lifecycle_on_loopback_synthetic_fixture_only(tmp_path):
    data = bytes(range(256)) * 4
    source = tmp_path / "synthetic.bin"
    source.write_bytes(data)
    payload = VerifiedPayload(source, hashlib.sha256(data).hexdigest(), len(data), data)
    service = adapter.ScopedTftpProcess(guard=lambda: True, output_dir=tmp_path / "loopback-adapter",
                                       test_mode=True, port=0)
    try:
        ready = service.start(payload, bind="127.0.0.1", client="127.0.0.2",
                              filename=source.name, timeout=3)
        assert ready["bind"] == "127.0.0.1" and ready["allow_client"] == "127.0.0.2"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.bind(("127.0.0.2", 0))
            client.settimeout(1)
            client.sendto(b"\x00\x01" + source.name.encode("ascii") + b"\0octet\0", (ready["bind"], ready["port"]))
            received = bytearray()
            for block in range(1, 4):
                packet, peer = client.recvfrom(2048)
                assert peer[0] == "127.0.0.1"
                assert struct.unpack("!HH", packet[:4]) == (3, block)
                received.extend(packet[4:])
                client.sendto(struct.pack("!HH", 4, block), peer)
            assert len(packet) == 4 and bytes(received) == data
        result = service.finish(timeout=3)
        assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER" and result["port"] == ready["port"]
        assert result["file"]["sha256"] == payload.expected_sha256
        assert service.close() is True
        assert not (service.output_dir / source.name).exists()
    finally:
        assert service.close() is True
