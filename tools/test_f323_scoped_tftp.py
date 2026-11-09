"""Synthetic fixtures and 127.0.0.1/127.0.0.2 only; no HGW, flash or firewall."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import queue
import socket
import struct
import subprocess
import sys
import threading
import time
from unittest.mock import Mock, patch

import pytest

import f323_scoped_tftp as tftp


TOOLS = Path(__file__).resolve().parent
NAME = "candidate.bin"
SENTINEL = "rejected-untrusted-name-or-error-DO-NOT-LOG"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request(name=NAME, opcode=tftp.OP_RRQ, mode=b"octet", options=()):
    filename = name.encode("ascii") if isinstance(name, str) else name
    packet = struct.pack("!H", opcode) + filename + b"\0" + mode + b"\0"
    for option, value in options:
        packet += option + b"\0" + value + b"\0"
    return packet


def ack(block):
    return struct.pack("!HH", tftp.OP_ACK, block)


def client_socket(address="127.0.0.1", port=0, timeout=1):
    assert address in {"127.0.0.1", "127.0.0.2"}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if hasattr(socket, "SIO_UDP_CONNRESET"):
        sock.ioctl(socket.SIO_UDP_CONNRESET, False)
    sock.bind((address, port))
    sock.settimeout(timeout)
    return sock


def receive_file(client, first=None):
    content = bytearray()
    blocks = []
    expected = 1
    transfer_peer = None
    while True:
        packet, peer = first if first is not None else client.recvfrom(2048)
        first = None
        assert peer[0] == "127.0.0.1"
        transfer_peer = transfer_peer or peer
        assert peer == transfer_peer
        assert len(packet) >= 4
        opcode, block = struct.unpack("!HH", packet[:4])
        assert opcode == tftp.OP_DATA
        if block == expected - 1:
            client.sendto(ack(block), peer)
            continue
        assert block == expected
        content.extend(packet[4:])
        blocks.append((block, len(packet) - 4))
        client.sendto(ack(block), peer)
        if len(packet) < 516:
            return bytes(content), blocks, peer
        expected += 1


class RunningServer:
    def __init__(self, payload, **options):
        self.events = []
        self.ready = queue.Queue()
        self.finished = queue.Queue()
        ready_hook = options.pop("ready_hook", None)

        def event(row):
            self.events.append(row)
            if row["event"] == "ready":
                if ready_hook:
                    ready_hook()
                self.ready.put((row["bind"], row["port"]))

        def run():
            try:
                self.finished.put(tftp.serve_once(payload, on_event=event, **options))
            except BaseException as error:
                self.finished.put(error)

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self.address = self.ready.get(timeout=3)

    def result(self, timeout=3):
        self.thread.join(timeout)
        assert not self.thread.is_alive(), "loopback fixture exceeded its bounded server timeout"
        result = self.finished.get_nowait()
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture
def start_server(tmp_path):
    servers = []

    def start(data=b"synthetic fixture", **overrides):
        source = tmp_path / f"fixture-{len(servers)}.bin"
        source.write_bytes(data)
        payload = tftp.load_verified_file(source, sha(data), len(data))
        options = dict(bind="127.0.0.1", allow_client="127.0.0.1", allow_file=NAME,
                       port=0, timeout=2, ack_timeout=0.08, max_retries=3)
        options.update(overrides)
        assert options["bind"] == "127.0.0.1"
        assert options["allow_client"] in {"127.0.0.1", "127.0.0.2"}
        server = RunningServer(payload, **options)
        server.source = source
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.thread.join(4)
        assert not server.thread.is_alive(), "loopback fixture leaked a server thread"


def test_256k_transfer_includes_empty_final_block_and_exact_buffer(start_server):
    data = bytes(range(256)) * 1024
    server = start_server(data, timeout=5)
    with client_socket() as client:
        client.sendto(request(), server.address)
        received, blocks, peer = receive_file(client)
    result = server.result()
    assert received == data and sha(received) == sha(data)
    assert blocks[-1] == (513, 0) and len(blocks) == 513
    assert peer[1] != server.address[1]
    assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER"
    assert result["counts"]["blocks_acked"] == 513
    assert result["counts"]["payload_bytes_acked"] == len(data)
    assert result["sockets_closed"] is True


def test_exact_5361664_synthetic_bytes_transfer_without_persisting_payload(tmp_path):
    size = 5_361_664
    data = bytes(range(256)) * (size // 256)
    expected_sha256 = sha(data)
    metadata_only_path = tmp_path / "synthetic-in-memory-only.bin"
    payload = tftp.VerifiedPayload(metadata_only_path, expected_sha256, size, data)
    server = RunningServer(payload, bind="127.0.0.1", allow_client="127.0.0.1", allow_file=NAME,
                           port=0, timeout=20, ack_timeout=0.15, max_retries=3)
    try:
        with client_socket(timeout=2) as client:
            client.sendto(request(), server.address)
            received, blocks, _ = receive_file(client)
        result = server.result()
        assert len(received) == size and received == data and sha(received) == expected_sha256
        assert len(blocks) == 10_473 and blocks[-1] == (10_473, 0)
        assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER" and result["sockets_closed"] is True
        assert result["counts"]["blocks_acked"] == 10_473
        assert result["counts"]["payload_bytes_acked"] == size
        assert result["file"]["sha256"] == expected_sha256
        assert not metadata_only_path.exists()
        assert not list(tmp_path.iterdir())
    finally:
        server.thread.join(21)
        assert not server.thread.is_alive()


@pytest.mark.parametrize("size", [0, 1, 511, 512, 513, 1024])
def test_partial_exact_multiple_and_empty_files_are_terminated_correctly(start_server, size):
    data = (b"0123456789abcdef" * (size // 16 + 1))[:size]
    server = start_server(data)
    with client_socket() as client:
        client.sendto(request(mode=b"OCTET"), server.address)
        received, blocks, _ = receive_file(client)
    assert received == data
    assert len(blocks) == size // 512 + 1
    assert blocks[-1][1] == size % 512
    assert server.result()["transfer_complete"] is True


@pytest.mark.parametrize("options", [
    ((b"blksize", b"1468"),), ((b"timeout", b"1"),), ((b"tsize", b"0"),),
    ((b"BLKSIZE", b"8192"), (b"Timeout", b"2"), (b"tsize", b"0")),
])
def test_rfc2347_options_fall_back_to_data1_and_512_without_oack(start_server, options):
    data = bytes(range(256)) * 8
    server = start_server(data)
    with client_socket() as client:
        client.sendto(request(options=options), server.address)
        first, peer = client.recvfrom(2048)
        assert struct.unpack("!HH", first[:4]) == (tftp.OP_DATA, 1)
        assert len(first) == 516
        received, blocks, _ = receive_file(client, (first, peer))
    result = server.result()
    assert received == data
    assert blocks == [(1, 512), (2, 512), (3, 512), (4, 512), (5, 0)]
    assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER"
    assert result["counts"]["rejected_requests"] == 0


@pytest.mark.parametrize("options", [
    ((b"blksize", b"1468"),), ((b"timeout", b"1"),), ((b"tsize", b"0"),),
    ((b"BLKSIZE", b"8192"), (b"Timeout", b"2"), (b"tsize", b"0")),
    ((b"unknown-option", b"unrecognized-value"),),
])
def test_parser_accepts_unique_ascii_option_pairs_for_ignored_negotiation(options):
    assert tftp.request_error(request(options=options), NAME.encode()) is None


@pytest.mark.parametrize("packet", [
    request() + b"blksize\0",
    request() + b"blksize\0" + b"1468",
    request(options=((b"", b"1468"),)),
    request(options=((b"blksize", b""),)),
    request(options=((b"blksize", b"1468"), (b"blksize", b"8192"))),
    request(options=((b"blksize", b"1468"), (b"BlKsIzE", b"8192"))),
    request(options=((b"timeout", b"1"), (b"TIMEOUT", b"2"))),
    request(options=((b"opt\xff", b"value"),)),
    request(options=((b"blksize", b"1468\xff"),)),
    request(options=((b"tsize", b"0"),)) + b"\0",
])
def test_parser_rejects_malformed_non_ascii_and_casefold_duplicate_options(packet):
    assert tftp.request_error(packet, NAME.encode()) == tftp.ERR_ILLEGAL


def test_request_512_byte_limit_is_inclusive_with_optional_fields():
    value = b"x" * (512 - len(request()) - len(b"x\0\0"))
    exact = request(options=((b"x", value),))
    assert len(exact) == 512
    assert tftp.request_error(exact, NAME.encode()) is None
    assert tftp.request_error(request(options=((b"x", value + b"x"),)), NAME.encode()) == tftp.ERR_ILLEGAL


@pytest.mark.parametrize("packet,code", [
    (request(SENTINEL), 2), (request("../candidate.bin"), 2), (request("/candidate.bin"), 2),
    (request("./candidate.bin"), 2), (request(r"folder\candidate.bin"), 2),
    (request("CANDIDATE.BIN"), 2), (request(b"candidate.bin\xff"), 2),
    (request(opcode=2), 2), (request(mode=b"netascii"), 4),
    (request() + b"blksize\0", 4), (request()[:-1], 4), (b"\0", 4),
    (request(options=((b"blksize", b"1024"), (b"BLKSIZE", b"512"))), 4),
    (request(options=((b"x", b"x" * 512),)), 4),
])
def test_writes_aliases_wrong_names_modes_and_malformed_rrq_are_rejected(start_server, packet, code):
    data = b"accepted fixture"
    server = start_server(data)
    with client_socket() as client:
        client.sendto(packet, server.address)
        response, peer = client.recvfrom(2048)
        assert peer == server.address
        assert struct.unpack("!HH", response[:4]) == (5, code)
        assert SENTINEL.encode() not in response
        client.sendto(request(), server.address)
        assert receive_file(client)[0] == data
    result = server.result()
    assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER"
    assert result["counts"]["rejected_requests"] == 1
    assert SENTINEL not in json.dumps(server.events)


def test_wrong_client_is_silent_before_parsing_then_exact_client_can_read(start_server):
    server = start_server(allow_client="127.0.0.2")
    with client_socket(timeout=0.1) as foreign:
        foreign.sendto(request(SENTINEL, opcode=2), server.address)
        with pytest.raises(socket.timeout):
            foreign.recvfrom(2048)
    with client_socket("127.0.0.2") as client:
        client.sendto(request(), server.address)
        assert receive_file(client)[0] == b"synthetic fixture"
    result = server.result()
    assert result["counts"]["foreign_client"] == 1
    assert result["counts"]["rejected_requests"] == 0
    assert SENTINEL not in json.dumps(server.events)


@pytest.mark.parametrize("bad_packet,metric", [
    (ack(1) + b"extra", "malformed_ack"), (ack(1)[:3], "malformed_ack"),
    (struct.pack("!HH", 3, 1), "malformed_ack"),
    (ack(0), "unexpected_ack"), (ack(2), "unexpected_ack"),
])
def test_ack_requires_exact_length_opcode_and_current_block(start_server, bad_packet, metric):
    data = b"f" * 600
    server = start_server(data)
    with client_socket() as client:
        client.sendto(request(), server.address)
        first, peer = client.recvfrom(2048)
        client.sendto(bad_packet, peer)
        resent, resent_peer = client.recvfrom(2048)
        assert (resent, resent_peer) == (first, peer)
        assert receive_file(client, (resent, peer))[0] == data
    result = server.result()
    assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER"
    assert result["counts"][metric] >= 1 and result["counts"]["retransmissions"] >= 1


@pytest.mark.parametrize("foreign_ip,same_tid", [("127.0.0.1", False), ("127.0.0.2", True)])
def test_wrong_transfer_peer_cannot_ack_or_abort(start_server, foreign_ip, same_tid):
    data = b"fixed receive tuple" * 40
    server = start_server(data)
    with client_socket() as client:
        client.sendto(request(), server.address)
        first, peer = client.recvfrom(2048)
        with client_socket(foreign_ip, client.getsockname()[1] if same_tid else 0) as foreign:
            foreign.sendto(ack(1), peer)
            foreign.sendto(struct.pack("!HH", 5, 0) + SENTINEL.encode() + b"\0", peer)
            resent, source = client.recvfrom(2048)
            assert (resent, source) == (first, peer)
            assert receive_file(client, (resent, peer))[0] == data
    result = server.result()
    assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER"
    assert result["counts"]["foreign_peer"] >= 2
    assert SENTINEL not in json.dumps(server.events)


def test_dropped_ack_retransmits_same_block_without_corrupting_content(start_server):
    data = bytes(range(256)) * 4
    server = start_server(data)
    with client_socket() as client:
        client.sendto(request(), server.address)
        first = client.recvfrom(2048)
        retry = client.recvfrom(2048)
        assert retry == first
        assert receive_file(client, retry)[0] == data
    result = server.result()
    assert result["counts"]["retransmissions"] >= 1
    assert result["counts"]["payload_bytes_acked"] == len(data)


def test_client_error_aborts_terminally_without_logging_message(start_server):
    server = start_server(b"payload" * 100)
    with client_socket() as client:
        client.sendto(request(), server.address)
        _, peer = client.recvfrom(2048)
        client.sendto(struct.pack("!HH", 5, 0) + SENTINEL.encode() + b"\0", peer)
    result = server.result()
    assert result["status"] == "FAIL_TFTP_SINGLE_TRANSFER" and result["reason"] == "client_error"
    assert result["transfer_started"] is True and result["transfer_complete"] is False
    assert result["sockets_closed"] is True
    assert SENTINEL not in json.dumps(server.events)


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_first_started_transfer_is_terminal_never_returns_to_listener(start_server, outcome):
    server = start_server(b"one session", max_retries=1, ack_timeout=0.04)
    with client_socket() as client:
        client.sendto(request(), server.address)
        if outcome == "success":
            receive_file(client)
        else:
            client.recvfrom(2048)  # Intentionally never ACK.
        result = server.result()
    assert result["status"] == ("PASS_TFTP_SINGLE_TRANSFER" if outcome == "success" else "FAIL_TFTP_SINGLE_TRANSFER")
    if outcome == "failure":
        assert result["reason"] == "ack_retries_exhausted"
        assert result["counts"]["data_packets_sent"] == 2
    with client_socket(timeout=0.12) as second:
        second.sendto(request(), server.address)
        with pytest.raises((socket.timeout, ConnectionResetError)):
            second.recvfrom(2048)
    assert sum(event["event"] == "transfer_started" for event in server.events) == 1


def test_global_deadline_bounds_waiting_under_foreign_request_flood(start_server):
    server = start_server(timeout=0.25)
    stopped = threading.Event()
    with client_socket("127.0.0.2") as foreign:
        def flood():
            while not stopped.is_set():
                foreign.sendto(request(SENTINEL), server.address)
                stopped.wait(0.003)
        worker = threading.Thread(target=flood, daemon=True)
        worker.start()
        try:
            result = server.result(timeout=1.5)
        finally:
            stopped.set()
            worker.join(1)
    assert result["reason"] == "global_timeout" and result["transfer_started"] is False
    assert result["counts"]["foreign_client"] > 0
    assert result["elapsed_seconds"] < 1


def test_listen_and_transfer_share_one_deadline_even_under_foreign_ack_flood(start_server):
    server = start_server(b"fixed" * 1000, timeout=0.45, ack_timeout=0.3, max_retries=20)
    stopped = threading.Event()
    with client_socket() as client, client_socket("127.0.0.2") as foreign:
        time.sleep(0.2)  # Spend almost half of the same deadline waiting for RRQ.
        client.sendto(request(), server.address)
        _, peer = client.recvfrom(2048)
        def flood():
            while not stopped.is_set():
                foreign.sendto(ack(1), peer)
                stopped.wait(0.003)
        worker = threading.Thread(target=flood, daemon=True)
        worker.start()
        try:
            result = server.result(timeout=1.5)
        finally:
            stopped.set()
            worker.join(1)
    assert result["reason"] == "global_timeout" and result["transfer_started"] is True
    assert result["counts"]["foreign_peer"] > 0
    assert result["counts"]["blocks_acked"] == 0
    assert 0.4 <= result["elapsed_seconds"] < 0.65


def test_replacing_source_after_ready_does_not_change_the_snapshot(tmp_path):
    source = tmp_path / "snapshot.bin"
    data = bytes(range(256)) * 64
    source.write_bytes(data)
    payload = tftp.load_verified_file(source, sha(data), len(data))
    server = RunningServer(payload, bind="127.0.0.1", allow_client="127.0.0.1", allow_file=NAME,
                           port=0, timeout=2, ack_timeout=0.1, max_retries=2,
                           ready_hook=lambda: source.write_bytes(b"entirely different bytes"))
    try:
        with client_socket() as client:
            client.sendto(request(), server.address)
            assert receive_file(client)[0] == data
        assert server.result()["status"] == "PASS_TFTP_SINGLE_TRANSFER"
        assert source.read_bytes() != data
    finally:
        server.thread.join(3)
        assert not server.thread.is_alive()


@pytest.mark.parametrize("value", ["0.0.0.0", "::1", "localhost", "224.0.0.1", "255.255.255.255", 123, True])
def test_bind_and_client_require_explicit_unicast_ipv4(value):
    with pytest.raises(ValueError):
        tftp.exact_ipv4(value)


@pytest.mark.parametrize("name", ["../candidate.bin", "/candidate.bin", r"folder\candidate.bin", "./candidate.bin",
                                 "", ".", "..", "x\0y", "café.bin", "a" * 129])
def test_allow_file_rejects_non_ascii_paths_and_aliases(name):
    with pytest.raises(ValueError):
        tftp.exact_filename(name)


def test_block_wrap_is_rejected_instead_of_reusing_zero_or_one():
    assert tftp.block_count(65535 * 512 - 1) == 65535
    with pytest.raises(ValueError):
        tftp.block_count(65535 * 512)
    with pytest.raises(ValueError):
        tftp.block_count(-1)


def test_correct_final_ack_arriving_after_global_deadline_cannot_pass(tmp_path):
    payload = tftp.VerifiedPayload(tmp_path / "synthetic.bin", sha(b"x"), 1, b"x")
    now = [0.0]
    peer = ("127.0.0.1", 12345)
    sock = Mock()
    sock.sendto.side_effect = lambda packet, _: len(packet)

    def late_ack(_):
        now[0] = 1.01
        return ack(1), peer

    sock.recvfrom.side_effect = late_ack
    counts = dict.fromkeys(("data_packets_sent", "data_bytes_sent_including_retries",
                           "transfer_datagrams_received", "blocks_acked", "payload_bytes_acked"), 0)
    with pytest.raises(tftp.TftpFailure, match="global_timeout"):
        tftp._send_payload(sock, payload, peer, deadline=1, ack_timeout=0.5,
                           max_retries=1, counts=counts, clock=lambda: now[0])
    assert counts["blocks_acked"] == 0 and counts["payload_bytes_acked"] == 0


@pytest.mark.parametrize("received_at", [0.5, 0.51])
def test_ack_at_or_after_attempt_deadline_is_not_accepted_before_global_deadline(tmp_path, received_at):
    payload = tftp.VerifiedPayload(tmp_path / "synthetic.bin", sha(b"x"), 1, b"x")
    now = [0.0]
    peer = ("127.0.0.1", 12345)
    sock = Mock()
    sock.sendto.side_effect = lambda packet, _: len(packet)

    def late_ack(_):
        now[0] = received_at
        return ack(1), peer

    sock.recvfrom.side_effect = late_ack
    counts = dict.fromkeys(("data_packets_sent", "data_bytes_sent_including_retries", "late_ack",
                           "transfer_datagrams_received", "blocks_acked", "payload_bytes_acked"), 0)
    with pytest.raises(tftp.TftpFailure, match="ack_retries_exhausted"):
        tftp._send_payload(sock, payload, peer, deadline=2, ack_timeout=0.5,
                           max_retries=0, counts=counts, clock=lambda: now[0])
    assert counts["late_ack"] == 1 and counts["blocks_acked"] == 0
    assert counts["payload_bytes_acked"] == 0


def test_expired_attempt_ack_forces_retry_before_a_timely_ack_can_finish(tmp_path):
    payload = tftp.VerifiedPayload(tmp_path / "synthetic.bin", sha(b"x"), 1, b"x")
    now = [0.0]
    arrivals = iter((0.51, 0.52))
    peer = ("127.0.0.1", 12345)
    sock = Mock()
    sock.sendto.side_effect = lambda packet, _: len(packet)

    def receive(_):
        now[0] = next(arrivals)
        return ack(1), peer

    sock.recvfrom.side_effect = receive
    counts = dict.fromkeys(("data_packets_sent", "data_bytes_sent_including_retries", "late_ack",
                           "transfer_datagrams_received", "blocks_acked", "payload_bytes_acked", "retransmissions"), 0)
    tftp._send_payload(sock, payload, peer, deadline=2, ack_timeout=0.5,
                       max_retries=1, counts=counts, clock=lambda: now[0])
    assert counts["late_ack"] == 1 and counts["retransmissions"] == 1
    assert counts["data_packets_sent"] == 2 and counts["blocks_acked"] == 1
    assert sock.sendto.call_args_list[0].args == sock.sendto.call_args_list[1].args


def test_payload_is_immutable_bounded_and_hash_size_checked(tmp_path):
    path = tmp_path / "fixture.bin"
    path.write_bytes(b"fixture")
    for digest, length in (("0" * 64, 7), (sha(b"fixture"), 8), (sha(b"fixture"), tftp.MAX_FILE_BYTES + 1)):
        with pytest.raises(ValueError):
            tftp.load_verified_file(path, digest, length)
    with pytest.raises(ValueError):
        tftp.VerifiedPayload(path, sha(b"fixture"), 7, bytearray(b"fixture"))
    payload = tftp.load_verified_file(path, sha(b"fixture"), 7)
    with pytest.raises(AttributeError):
        payload.data = b"changed"
    assert "fixture'" not in repr(payload)


@pytest.mark.parametrize("field,value", [("timeout", 0), ("timeout", float("inf")), ("timeout", float("nan")),
                                        ("max_retries", 21), ("max_retries", -1), ("ack_timeout", 0), ("port", -1)])
def test_invalid_transport_bounds_are_rejected_before_binding(field, value):
    options = dict(bind="127.0.0.1", allow_client="127.0.0.1", allow_file=NAME,
                   port=0, timeout=1, ack_timeout=0.1, max_retries=1)
    options[field] = value
    with pytest.raises(ValueError):
        tftp.validate_scope(**options)


def cli_args(source, data, output):
    return ["--file", str(source), "--expected-sha256", sha(data), "--expected-bytes", str(len(data)),
            "--bind", "127.0.0.1", "--allow-client", "127.0.0.1", "--allow-file", NAME,
            "--port", "0", "--timeout", "5", "--output-dir", str(output)]


def test_cli_default_is_plan_without_socket_or_output_mutation(tmp_path):
    source, output, data = tmp_path / "fixture.bin", tmp_path / "plan", b"offline fixture"
    source.write_bytes(data)
    with patch.object(tftp.socket, "socket", side_effect=AssertionError("plan attempted a socket")) as factory, \
            redirect_stdout(io.StringIO()) as stdout:
        assert tftp.main(cli_args(source, data, output)) == 0
    factory.assert_not_called()
    result = json.loads(stdout.getvalue())
    assert result["status"] == "PASS_OFFLINE_TFTP_PLAN"
    assert result["network_access"] is False and not output.exists()


def test_cli_hash_failure_or_existing_output_stops_before_any_socket(tmp_path):
    source, output, data = tmp_path / "fixture.bin", tmp_path / "output", b"offline fixture"
    source.write_bytes(data)
    args = cli_args(source, data, output) + ["--execute"]
    args[args.index("--expected-sha256") + 1] = "0" * 64
    with patch.object(tftp.socket, "socket", side_effect=AssertionError("bad preflight attempted a socket")) as factory, \
            redirect_stdout(io.StringIO()):
        assert tftp.main(args) == 2
        output.mkdir()
        assert tftp.main(cli_args(source, data, output) + ["--execute"]) == 2
    factory.assert_not_called()


def test_cli_ready_json_and_final_evidence_have_no_payload_or_rejected_name(tmp_path):
    source, output, data = tmp_path / "fixture.bin", tmp_path / "evidence", b"SYNTHETIC_PAYLOAD_NOT_IN_LOGS" * 50
    source.write_bytes(data)
    process = subprocess.Popen([sys.executable, "-B", str(TOOLS / "f323_scoped_tftp.py"),
                                *cli_args(source, data, output), "--execute"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        ready = json.loads(process.stdout.readline())
        assert ready["event"] == "ready" and ready["bind"] == "127.0.0.1" and ready["port"] > 0
        with client_socket() as client:
            address = ready["bind"], ready["port"]
            client.sendto(request(SENTINEL), address)
            assert struct.unpack("!H", client.recvfrom(2048)[0][:2])[0] == 5
            client.sendto(request(), address)
            assert receive_file(client)[0] == data
        stdout, stderr = process.communicate(timeout=3)
        assert process.returncode == 0 and stderr == ""
        evidence = (output / "result.json").read_text()
        events = (output / "events.jsonl").read_text()
        result = json.loads(evidence)
        assert result["status"] == "PASS_TFTP_SINGLE_TRANSFER" and result["flash"] is False
        for text in (stdout, evidence, events):
            assert SENTINEL not in text and "SYNTHETIC_PAYLOAD_NOT_IN_LOGS" not in text
        assert {path.name for path in output.iterdir()} == {"result.json", "events.jsonl"}
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=3)
