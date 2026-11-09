"""Loopback-only transfers and mocked runner failures; no UART/router/flash."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import socket
import struct
import subprocess
import sys
from unittest.mock import Mock

import pytest


TOOLS = Path(__file__).resolve().parent


@pytest.fixture
def scoped_server(tmp_path):
    payload = bytes(range(256)) * 4  # Exact block multiple exercises final empty block.
    (tmp_path / "candidate.bin").write_bytes(payload)
    (tmp_path / "not-allowed.bin").write_bytes(b"private fixture")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = subprocess.Popen([
        sys.executable, str(TOOLS / "tftp_serve_once.py"), "--root", str(tmp_path),
        "--bind", "127.0.0.1", "--port", str(port), "--allow-client", "127.0.0.1",
        "--allow-file", "candidate.bin", "--once", "--timeout", "5",
        "--ack-timeout", "0.2", "--retries", "3",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert "TFTP read-only server" in process.stdout.readline()
        yield process, ("127.0.0.1", port), payload
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)


def request(name="candidate.bin", opcode=1):
    return struct.pack("!H", opcode) + name.encode() + b"\0octet\0"


def receive_candidate(address):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.bind(("127.0.0.1", 0))
        client.settimeout(2)
        client.sendto(request(), address)
        result = bytearray()
        expected_block = 1
        while True:
            data, peer = client.recvfrom(1024)
            assert peer[0] == "127.0.0.1"  # Transfer socket uses scoped interface too.
            assert struct.unpack("!HH", data[:4]) == (3, expected_block)
            result.extend(data[4:])
            client.sendto(struct.pack("!HH", 4, expected_block), peer)
            if len(data) < 516:
                return bytes(result)
            expected_block += 1


def test_exact_file_transfer_and_final_empty_block(scoped_server):
    process, address, payload = scoped_server
    assert receive_candidate(address) == payload
    assert process.wait(timeout=3) == 0


@pytest.mark.parametrize("name,opcode", [
    ("not-allowed.bin", 1), ("../candidate.bin", 1),
    ("/candidate.bin", 1), ("candidate.bin", 2),
])
def test_other_files_aliases_and_writes_rejected(scoped_server, name, opcode):
    process, address, payload = scoped_server
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.bind(("127.0.0.1", 0))
        client.settimeout(2)
        client.sendto(request(name, opcode), address)
        data, peer = client.recvfrom(1024)
        assert peer == address
        assert struct.unpack("!HH", data[:4]) == (5, 2)
    assert receive_candidate(address) == payload
    assert process.wait(timeout=3) == 0


def test_other_client_ignored_before_serving(scoped_server):
    process, address, payload = scoped_server
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.bind(("127.0.0.2", 0))
        client.settimeout(0.3)
        client.sendto(request(), address)
        with pytest.raises(socket.timeout):
            client.recvfrom(1024)
    assert receive_candidate(address) == payload
    assert process.wait(timeout=3) == 0


def load_runner():
    spec = importlib.util.spec_from_file_location("scoped_tftp_runner", TOOLS /
        "run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("failure", ["hash", "listener", "backend"])
def test_runner_isolated_copy_and_cleanup_before_or_after_backend(tmp_path, monkeypatch, failure):
    runner = load_runner()
    original = tmp_path / "source" / "candidate.bin"
    original.parent.mkdir()
    original.write_bytes(b"synthetic candidate")
    monkeypatch.setattr(runner, "CANDIDATE", original)
    monkeypatch.setattr(runner, "EXPECTED_BYTES", original.stat().st_size)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    monkeypatch.setattr(runner, "EXPECTED_SHA256", "0" * 64 if failure == "hash" else digest)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    listener = Mock()
    listener.poll.return_value = 3 if failure == "listener" else None
    listener.stdout.read.return_value = "synthetic listener log"
    start = Mock(return_value=listener)
    monkeypatch.setattr(runner, "start_tftp", start)
    backend = Mock(return_value=subprocess.CompletedProcess([], 1, "synthetic backend rejection"))
    monkeypatch.setattr(runner.subprocess, "run", backend)
    attempt = tmp_path / "attempt"
    args = argparse.Namespace(evidence_dir=attempt, transport="tftp", external_tftp=False,
        timeout=600, server_ip="127.0.0.1", client_ip="127.0.0.2", host="127.0.0.2",
        port="OFFLINE-NOT-A-PORT", erase_bytes=0x5e0000, skip_bootbase_ping=False, attempt_id=None)
    values = dict.fromkeys(["rollback_sha256", "rollback_crc32", "current_live_crc32",
        "candidate_crc32", "expected_full_slot_sha256", "expected_full_slot_crc32"], "synthetic")
    for key in ("protected_partition_sha256", "protected_partition_crc32"):
        values[key] = dict.fromkeys(["mtd0", "mtd1", "mtd2", "mtd5"], "synthetic")
    with pytest.raises(RuntimeError):
        runner.execute_backend(args, values)
    assert original.read_bytes() == b"synthetic candidate"
    assert not (attempt / "tftp-only").exists()
    assert (attempt / "tftp.log").exists()
    if failure == "hash":
        start.assert_not_called()
    else:
        start.assert_called_once_with(600, attempt / "tftp-only", "127.0.0.1", "127.0.0.2", "candidate.bin")
    if failure == "backend":
        backend.assert_called_once()
        command = backend.call_args.args[0]
        assert command[command.index("-Candidate") + 1] == str(attempt / "tftp-only" / "candidate.bin")
        listener.terminate.assert_called_once()
    else:
        backend.assert_not_called()


def test_listener_command_pins_address_client_and_file(monkeypatch, tmp_path):
    runner = load_runner()
    popen = Mock()
    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    runner.start_tftp(600, tmp_path, "127.0.0.1", "127.0.0.2", "candidate.bin")
    command = popen.call_args.args[0]
    for flag, value in [("--root", str(tmp_path)), ("--bind", "127.0.0.1"),
                        ("--allow-client", "127.0.0.2"), ("--allow-file", "candidate.bin")]:
        assert command[command.index(flag) + 1] == value
    assert "0.0.0.0" not in command
