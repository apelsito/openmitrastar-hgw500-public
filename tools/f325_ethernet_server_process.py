"""Guarded one-shot process adapter for the reviewed scoped TFTP server.

Construction has no external effects. No CLI or physical guard is provided.
Production uses the RAM core's port-69 contract; explicit test mode permits
only loopback addresses and an ephemeral port. Firmware is never copied.
"""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from f325_ethernet_ram_gate import sanitize_server_result, verify_ready, verify_server_result
from f325_scoped_tftp import EVENT_SCHEMA, VerifiedPayload, validate_scope


SERVER_SHA256 = "d4922784174d8e58d1aba60d5844c4fdc1e553159141a27ad43e6d1685ec5488"
SERVER_SOURCE = Path(__file__).resolve().with_name("f325_scoped_tftp.py")
MAX_SOURCE_BYTES = 262144
MAX_LOG_BYTES = 262144
MAX_RESULT_BYTES = 65536
MAX_EVENT_BYTES = 65536


class ServerProcessFailure(RuntimeError):
    """Only fixed adapter-defined codes are exposed; never raw child output."""


def _positive_timeout(value, maximum: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
        raise ServerProcessFailure("invalid_timeout")
    return float(value)


def _json_object(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError("non-finite number")

    try:
        value = json.loads(raw.decode("ascii"), object_pairs_hook=unique, parse_constant=reject_constant)
    except (ValueError, UnicodeError):
        raise ServerProcessFailure("invalid_json") from None
    if not isinstance(value, dict):
        raise ServerProcessFailure("invalid_json_object")
    return value


def _bounded_read(path: Path, maximum: int) -> bytes:
    if path.is_symlink():
        raise ServerProcessFailure("evidence_symlink")
    if not path.is_file():
        raise ServerProcessFailure("regular_file_required")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ServerProcessFailure("evidence_size_limit")
    return raw


def read_jsonl(path: Path, *, eof: bool = False) -> tuple[list[dict], bool]:
    """Read only completed lines; an active writer's final fragment is pending."""
    raw = _bounded_read(path, MAX_LOG_BYTES)
    lines = raw.split(b"\n")
    tail = bool(lines[-1])
    if eof and tail:
        raise ServerProcessFailure("incomplete_jsonl_at_exit")
    completed = lines[:-1]
    if len(completed) > 8:
        raise ServerProcessFailure("ambiguous_event_count")
    result = []
    for line in completed:
        if not line or len(line) > MAX_EVENT_BYTES:
            raise ServerProcessFailure("invalid_event_line")
        result.append(_json_object(line))
    return result, tail


class ScopedTftpProcess:
    def __init__(self, *, guard, output_dir: Path, server_source: Path = SERVER_SOURCE,
                 test_mode: bool = False, port: int = 69, ready_timeout: float = 15,
                 popen_factory=subprocess.Popen, clock=time.monotonic, sleep=time.sleep):
        if not callable(guard):
            raise ServerProcessFailure("guard_required")
        if type(test_mode) is not bool:
            raise ServerProcessFailure("test_mode_requires_bool")
        if type(port) is not int or port != (0 if test_mode else 69):
            raise ServerProcessFailure("invalid_adapter_port")
        self.guard, self.output_dir = guard, Path(output_dir)
        self.server_source = Path(server_source)
        self.test_mode, self.port = test_mode, port
        self.ready_timeout = _positive_timeout(ready_timeout, 15)
        self._popen, self._clock, self._sleep = popen_factory, clock, sleep
        self._attempted = self._launch_requested = False
        self._process = None
        self._handles = []
        self._ready = self._finished = None
        self._payload = None
        self._bind = self._client = self._filename = None
        self._timeout = None

    def _guard(self) -> None:
        try:
            confirmed = self.guard()
        except Exception:
            raise ServerProcessFailure("guard_failed") from None
        if confirmed is not True:
            raise ServerProcessFailure("guard_unconfirmed")

    def _configure(self, payload, bind, client, filename, timeout) -> None:
        if type(payload) is not VerifiedPayload or not isinstance(payload.source_path, Path) or not payload.source_path.is_absolute():
            raise ServerProcessFailure("unverified_payload")
        bind, client, _ = validate_scope(bind, client, filename, self.port, timeout, 0.5, 5)
        if filename != payload.source_path.name:
            raise ServerProcessFailure("filename_must_match_source_basename")
        if self.test_mode:
            if (not ipaddress.IPv4Address(bind).is_loopback or not ipaddress.IPv4Address(client).is_loopback
                    or timeout > 30):
                raise ServerProcessFailure("test_mode_is_loopback_only")
        else:
            subnet = ipaddress.IPv4Network("192.168.1.0/24")
            server = ipaddress.IPv4Address(bind)
            if (client != "192.168.1.90" or server not in subnet or bind == client
                    or server in {subnet.network_address, subnet.broadcast_address} or timeout != 300):
                raise ServerProcessFailure("production_network_contract")
        self._payload, self._bind, self._client, self._filename = payload, bind, client, filename
        self._timeout = float(timeout)

    def _create_snapshot(self) -> None:
        source = _bounded_read(self.server_source, MAX_SOURCE_BYTES)
        if hashlib.sha256(source).hexdigest() != SERVER_SHA256:
            raise ServerProcessFailure("server_source_hash")
        root = self.output_dir.absolute()
        for path in (root, *root.parents):
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ServerProcessFailure("output_symlink_or_junction")
        root.mkdir(parents=True, exist_ok=False)
        self.output_dir = root.resolve()
        self._snapshot = self.output_dir / "f325_scoped_tftp.py"
        with self._snapshot.open("xb") as stream:
            if stream.write(source) != len(source):
                raise ServerProcessFailure("snapshot_short_write")
            stream.flush()
            os.fsync(stream.fileno())
        if hashlib.sha256(_bounded_read(self._snapshot, MAX_SOURCE_BYTES)).hexdigest() != SERVER_SHA256:
            raise ServerProcessFailure("snapshot_hash")
        self._stdout_path = self.output_dir / "child.stdout.jsonl"
        self._stderr_path = self.output_dir / "child.stderr.log"
        self._result_path = self.output_dir / "server" / "result.json"

    def _exit_code(self):
        code = self._process.poll()
        if code is not None and type(code) is not int:
            raise ServerProcessFailure("process_exit_unproved")
        return code

    def _validate_ready(self, ready: dict) -> dict:
        if not self.test_mode:
            verify_ready(ready, self._payload, self._bind, self._client)
        else:
            port = ready.get("port")
            if type(port) is not int or not 1 <= port <= 65535:
                raise ServerProcessFailure("invalid_test_listener_port")
            # Only this validation view adapts the two test-only differences.
            # The returned ready record retains the actual port and timeout.
            view = dict(ready, port=69, timeout_seconds=300)
            if (type(ready.get("timeout_seconds")) not in (int, float)
                    or ready["timeout_seconds"] != self._timeout):
                raise ServerProcessFailure("test_listener_timeout")
            verify_ready(view, self._payload, self._bind, self._client)
        return {"schema": EVENT_SCHEMA, "event": "ready", "bind": self._bind, "port": ready["port"],
                "allow_client": self._client, "allow_file": self._filename,
                "file": self._payload.metadata(), "timeout_seconds": self._timeout}

    def _wait_ready(self) -> dict:
        deadline = self._clock() + self.ready_timeout
        while self._clock() < deadline:
            if self._exit_code() is not None:
                raise ServerProcessFailure("child_exited_before_ready")
            records, partial = read_jsonl(self._stdout_path)
            if records:
                if len(records) != 1:
                    raise ServerProcessFailure("unexpected_startup_events")
                ready = self._validate_ready(records[0])
                if not partial:
                    if self._exit_code() is not None:
                        raise ServerProcessFailure("child_exited_before_ready")
                    if self._clock() >= deadline:
                        raise ServerProcessFailure("ready_timeout")
                    return ready
            self._sleep(min(0.05, max(0, deadline - self._clock())))
        raise ServerProcessFailure("ready_timeout")

    def start(self, payload: VerifiedPayload, *, bind, client, filename, timeout=300) -> dict:
        if self._attempted:
            raise ServerProcessFailure("start_is_one_shot")
        self._attempted = True
        self._guard()
        try:
            self._configure(payload, bind, client, filename, timeout)
            self._create_snapshot()
            stdout = self._stdout_path.open("xb", buffering=0)
            self._handles.append(stdout)
            stderr = self._stderr_path.open("xb", buffering=0)
            self._handles.append(stderr)
            args = [sys.executable, "-I", "-B", str(self._snapshot), "--execute",
                    "--file", str(payload.source_path), "--expected-sha256", payload.expected_sha256,
                    "--expected-bytes", str(payload.expected_bytes), "--bind", self._bind,
                    "--allow-client", self._client, "--allow-file", self._filename,
                    "--timeout", str(self._timeout), "--port", str(self.port),
                    "--output-dir", str(self._result_path.parent)]
            self._guard()
            self._launch_requested = True
            self._process = self._popen(args, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                        shell=False, close_fds=True, cwd=str(self.output_dir),
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
            self._ready = self._wait_ready()
            return copy.deepcopy(self._ready)
        except Exception as error:
            self.close()
            if type(error) is ServerProcessFailure:
                raise
            raise ServerProcessFailure("start_contract_failed") from None

    def _validated_result(self, raw: dict) -> dict:
        if raw.get("script_sha256") != SERVER_SHA256:
            raise ServerProcessFailure("executed_server_hash")
        result = sanitize_server_result(raw, self._payload, self._bind, self._client)
        if self.test_mode:
            if (type(result.get("port")) is not int or result["port"] != self._ready["port"]
                    or result.get("timeout_seconds") != self._timeout):
                raise ServerProcessFailure("test_result_endpoint")
            view = dict(result, port=69, timeout_seconds=300)
            verify_server_result(view, self._payload, self._bind, self._client)
        else:
            verify_server_result(result, self._payload, self._bind, self._client)
        return result

    def finish(self, timeout=10) -> dict:
        budget = _positive_timeout(timeout, 10)
        if self._ready is None or self._process is None:
            raise ServerProcessFailure("server_not_ready")
        try:
            began = self._clock()
            code = self._process.wait(timeout=budget)
            if self._clock() - began > budget:
                raise ServerProcessFailure("finish_timeout")
            if type(code) is not int or self._exit_code() != code:
                raise ServerProcessFailure("process_exit_unproved")
            if code != 0:
                raise ServerProcessFailure("child_failed")
            if self._finished is not None:
                return copy.deepcopy(self._finished)
            records, _ = read_jsonl(self._stdout_path, eof=True)
            if ([row.get("schema") for row in records] != [EVENT_SCHEMA] * 3
                    or [row.get("event") for row in records] != ["ready", "transfer_started", "complete"]):
                raise ServerProcessFailure("terminal_event_sequence")
            if self._validate_ready(records[0]) != self._ready:
                raise ServerProcessFailure("ready_changed")
            if _bounded_read(self._stderr_path, MAX_LOG_BYTES):
                raise ServerProcessFailure("unexpected_stderr")
            raw = _json_object(_bounded_read(self._result_path, MAX_RESULT_BYTES))
            result = self._validated_result(raw)
            terminal = sanitize_server_result(records[2].get("result"), self._payload, self._bind, self._client)
            if terminal != result:
                raise ServerProcessFailure("terminal_result_mismatch")
            started = records[1]
            if (started.get("client") != self._client
                    or type(started.get("client_tid")) is not int or started["client_tid"] != result["client_tid"]
                    or type(started.get("transfer_tid")) is not int or started["transfer_tid"] != result["transfer_tid"]
                    or started.get("file") != self._payload.metadata()):
                raise ServerProcessFailure("transfer_event_mismatch")
            if self._clock() - began > budget:
                raise ServerProcessFailure("finish_timeout")
            self._finished = result
            return copy.deepcopy(result)
        except Exception as error:
            self.close()
            if isinstance(error, subprocess.TimeoutExpired):
                raise ServerProcessFailure("child_still_running") from None
            if type(error) is ServerProcessFailure:
                raise
            raise ServerProcessFailure("finish_contract_failed") from None

    def close(self) -> bool:
        confirmed = not self._launch_requested
        try:
            if self._process is not None:
                code = self._exit_code()
                if code is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=2)
                code = self._exit_code()
                waited = self._process.wait(timeout=0)
                confirmed = type(code) is int and type(waited) is int and waited == code
        except Exception:
            confirmed = False
        finally:
            remaining = []
            for handle in self._handles:
                try:
                    handle.close()
                except Exception:
                    confirmed = False
                    remaining.append(handle)
            self._handles = remaining
        return confirmed
