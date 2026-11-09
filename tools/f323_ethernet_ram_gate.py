"""Offline protocol core for a future, separately reviewed Ethernet RAM gate.

There is no CLI, UART/network adapter, boot acquisition or physical execution
path here. The caller supplies already-owned adapters and a strict live guard.
RAM protocol success cannot attest that those adapters are real or reviewed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import math
from pathlib import Path
import re
import time
import zlib

from f323_scoped_tftp import EVENT_SCHEMA, RESULT_SCHEMA, VerifiedPayload, block_count, exact_filename, exact_ipv4


SCHEMA = "openmitrastar.f323-ethernet-ram-gate/v1"
PASS = "PASS_ETHERNET_RAM_GATE"
FAIL = "FAIL_ETHERNET_RAM_GATE"
CLIENT_IPV4 = "192.168.1.90"
ADDRESS = "0x83000000"
CRC_ADDRESS = "0x84000000"
SERVER_TIMEOUT = 300
MAX_TRANSCRIPT_BYTES = 131072
DEVICE_FIRMWARE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"


@dataclass(frozen=True)
class ImagePin:
    name: str
    source_path: Path
    sha256: str
    byte_count: int
    crc32: str


_PINS = (
    ImagePin("f323", DEVICE_FIRMWARE / "f323-f321-browser-compat-device-bound" /
             "openmitrastar-linux510-f323-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin",
             "9d8dbd5bd9a6c372e95d8f6365396f8eb4695ab61848cd49341d76fee2153c11", 5361664, "81cec636"),
    ImagePin("f321", DEVICE_FIRMWARE / "f321-f314-device-bound" /
             "openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin",
             "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18", 5337088, "bd1135df"),
)


class GateFailure(Exception):
    """Fixed local codes only; never include a transcript or adapter exception."""

    _codes = frozenset({
        "unverified_payload", "source_path", "unsupported_source_or_image", "payload_identity",
        "transcript_bounds", "transcript_encoding", "transcript_control_bytes", "topaz_prompt_missing",
        "ambiguous_prompt_or_echo", "bootloader_error", "unexpected_setenv_output", "environment_readback",
        "ambiguous_transfer_count", "transfer_count", "ambiguous_filesize", "filesize", "iminfo",
        "ambiguous_crc_address", "ram_crc", "ambiguous_crc_summary", "discordant_crc_summary",
        "unexpected_crc_output", "server_ready_contract", "server_result_contract", "server_tid_contract",
        "server_count_contract", "guard_not_confirmed", "server_lifetime_expired", "channel_timeout_contract",
        "network_authorization_required", "network_scope", "server_finish_timeout",
    })

    def __init__(self, code: str):
        self.code = code if isinstance(code, str) and code in self._codes else "adapter_or_input_error"
        super().__init__(self.code)


def validate_payload(payload: VerifiedPayload) -> ImagePin:
    if type(payload) is not VerifiedPayload or type(payload.data) is not bytes:
        raise GateFailure("unverified_payload")
    if not isinstance(payload.source_path, Path) or not payload.source_path.is_absolute():
        raise GateFailure("source_path")
    matches = [pin for pin in _PINS if payload.source_path == pin.source_path
               and payload.expected_sha256 == pin.sha256 and payload.expected_bytes == pin.byte_count]
    if len(matches) != 1:
        raise GateFailure("unsupported_source_or_image")
    pin = matches[0]
    if (len(payload.data) != pin.byte_count or hashlib.sha256(payload.data).hexdigest() != pin.sha256
            or f"{zlib.crc32(payload.data) & 0xffffffff:08x}" != pin.crc32):
        raise GateFailure("payload_identity")
    exact_filename(pin.source_path.name)
    return pin


def response_lines(response: bytes, command: str) -> list[str]:
    """Remove at most this command's echo, then require one fresh final prompt."""
    if type(response) is not bytes or not response or len(response) > MAX_TRANSCRIPT_BYTES:
        raise GateFailure("transcript_bounds")
    try:
        text = response.decode("ascii")
    except UnicodeDecodeError:
        raise GateFailure("transcript_encoding") from None
    if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
        raise GateFailure("transcript_control_bytes")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines or not re.fullmatch(r"topaz>[ \t]*", lines[-1]):
        raise GateFailure("topaz_prompt_missing")
    lines.pop()
    if lines and lines[0] in {command, "topaz> " + command, "topaz>" + command}:
        lines.pop(0)
    if any("topaz>" in line or line == command for line in lines):
        raise GateFailure("ambiguous_prompt_or_echo")
    failure = re.compile(r"\b(?:error|failed|failure|timeout|aborted)\b|bad (?:crc|magic)|unknown command|"
                         r"not found|retry count exceeded|^usage:", re.I)
    if any(failure.search(line) for line in lines):
        raise GateFailure("bootloader_error")
    return [line for line in lines if line.strip()]


def verify_silent(response: bytes, command: str) -> None:
    if response_lines(response, command):
        raise GateFailure("unexpected_setenv_output")


def verify_environment(response: bytes, command: str, name: str, value: str) -> None:
    if response_lines(response, command) != [name + "=" + value]:
        raise GateFailure("environment_readback")


def verify_transfer(response: bytes, command: str, expected_bytes: int) -> None:
    lines = response_lines(response, command)
    candidates = [line for line in lines if "Bytes transferred" in line]
    if len(candidates) != 1:
        raise GateFailure("ambiguous_transfer_count")
    match = re.fullmatch(r"Bytes transferred = ([0-9]+) \(([0-9a-fA-F]+) hex\)", candidates[0])
    if not match or int(match[1], 10) != expected_bytes or int(match[2], 16) != expected_bytes:
        raise GateFailure("transfer_count")


def verify_filesize(response: bytes, command: str, expected_bytes: int) -> None:
    lines = response_lines(response, command)
    if len(lines) != 1:
        raise GateFailure("ambiguous_filesize")
    match = re.fullmatch(r"filesize=([0-9a-fA-F]+)", lines[0])
    if not match or int(match[1], 16) != expected_bytes:
        raise GateFailure("filesize")


def verify_iminfo(response: bytes, command: str) -> None:
    lines = response_lines(response, command)
    addresses = [line for line in lines if "Checking Image" in line]
    checksums = [line.strip() for line in lines if "Verifying Checksum" in line]
    if addresses != ["## Checking Image at 83000000 ..."] or checksums != ["Verifying Checksum ... OK"]:
        raise GateFailure("iminfo")


def verify_crc(response: bytes, command: str, pin: ImagePin) -> str:
    lines = response_lines(response, command)
    words = [line for line in lines if re.match(r"^[0-9a-fA-F]{8}:", line)]
    if len(words) != 1:
        raise GateFailure("ambiguous_crc_address")
    # md.l ... 1 prints one word, optionally followed by its four ASCII chars.
    match = re.fullmatch(r"84000000:[ \t]+([0-9a-fA-F]{8})(?:[ \t]{2,}[ -~]{4})?[ \t]*", words[0])
    if not match or match[1].lower() != pin.crc32:
        raise GateFailure("ram_crc")
    summaries = [line for line in lines if line.startswith("CRC32")]
    if summaries:
        expected_end = int(ADDRESS, 16) + pin.byte_count - 1
        if len(summaries) != 1:
            raise GateFailure("ambiguous_crc_summary")
        summary = re.fullmatch(r"CRC32 for ([0-9a-fA-F]{8}) \.\.\. ([0-9a-fA-F]{8}) ==> ([0-9a-fA-F]{8})", summaries[0])
        if (not summary or int(summary[1], 16) != int(ADDRESS, 16)
                or int(summary[2], 16) != expected_end or summary[3].lower() != pin.crc32):
            raise GateFailure("discordant_crc_summary")
    if len(lines) != len(words) + len(summaries):
        raise GateFailure("unexpected_crc_output")
    return match[1].lower()


def _same_file_metadata(row, payload: VerifiedPayload) -> bool:
    return (isinstance(row, dict) and row.get("path") == str(payload.source_path)
            and row.get("sha256") == payload.expected_sha256
            and type(row.get("bytes")) is int and row["bytes"] == payload.expected_bytes
            and type(row.get("blocks_including_terminal")) is int
            and row["blocks_including_terminal"] == block_count(payload.expected_bytes))


def verify_ready(ready, payload: VerifiedPayload, server_ipv4: str, client_ipv4: str) -> None:
    if (not isinstance(ready, dict) or ready.get("schema") != EVENT_SCHEMA or ready.get("event") != "ready"
            or ready.get("bind") != server_ipv4 or type(ready.get("port")) is not int or ready["port"] != 69
            or ready.get("allow_client") != client_ipv4 or ready.get("allow_file") != payload.source_path.name
            or type(ready.get("timeout_seconds")) not in (int, float) or ready["timeout_seconds"] != SERVER_TIMEOUT
            or not _same_file_metadata(ready.get("file"), payload)):
        raise GateFailure("server_ready_contract")


_COUNTERS = ("listener_datagrams_received", "foreign_client", "rejected_requests", "transfer_datagrams_received",
             "foreign_peer", "malformed_ack", "unexpected_ack", "late_ack", "data_packets_sent",
             "data_bytes_sent_including_retries", "retransmissions", "blocks_acked", "payload_bytes_acked")
_REASONS = {None, "global_timeout", "short_datagram_send", "client_error", "ack_retries_exhausted",
            "server_error", "socket_close_unproved"}


def sanitize_server_result(raw, payload: VerifiedPayload, server_ipv4: str, client_ipv4: str) -> dict:
    """Keep only bounded typed scoped-server fields; ignore any raw adapter data."""
    if not isinstance(raw, dict):
        return {}
    result = {}
    exact = {"schema": RESULT_SCHEMA, "bind": server_ipv4, "allow_client": client_ipv4,
             "allow_file": payload.source_path.name}
    for key, value in exact.items():
        if raw.get(key) == value:
            result[key] = value
    if raw.get("status") in {"PASS_TFTP_SINGLE_TRANSFER", "FAIL_TFTP_SINGLE_TRANSFER"}:
        result["status"] = raw["status"]
    reason = raw.get("reason")
    if reason is None or isinstance(reason, str) and reason in _REASONS:
        result["reason"] = reason
    for key in ("port", "client_tid", "transfer_tid", "max_retries"):
        if type(raw.get(key)) is int and 0 <= raw[key] <= 65535:
            result[key] = raw[key]
    for key in ("timeout_seconds", "ack_timeout_seconds", "elapsed_seconds"):
        if type(raw.get(key)) in (int, float) and math.isfinite(raw[key]) and 0 <= raw[key] <= 3600:
            result[key] = raw[key]
    for key in ("transfer_started", "transfer_complete", "raw_content_logged", "rejected_filenames_logged",
                "flash", "boot_verified", "sockets_closed"):
        if type(raw.get(key)) is bool:
            result[key] = raw[key]
    if _same_file_metadata(raw.get("file"), payload):
        result["file"] = payload.metadata()
    counts = raw.get("counts")
    if isinstance(counts, dict):
        result["counts"] = {key: counts[key] for key in _COUNTERS
                            if type(counts.get(key)) is int and 0 <= counts[key] <= 2**63 - 1}
    return result


def verify_server_result(result: dict, payload: VerifiedPayload, server_ipv4: str, client_ipv4: str) -> None:
    required = {"schema": RESULT_SCHEMA, "status": "PASS_TFTP_SINGLE_TRANSFER", "reason": None,
                "bind": server_ipv4, "port": 69, "allow_client": client_ipv4,
                "allow_file": payload.source_path.name, "timeout_seconds": SERVER_TIMEOUT,
                "transfer_started": True, "transfer_complete": True, "sockets_closed": True,
                "raw_content_logged": False, "rejected_filenames_logged": False, "flash": False, "boot_verified": False}
    if (any(key not in result or type(result[key]) is not type(value) and not
            (key == "timeout_seconds" and type(result[key]) in (int, float)) or result.get(key) != value
            for key, value in required.items()) or not _same_file_metadata(result.get("file"), payload)):
        raise GateFailure("server_result_contract")
    if (not 1 <= result.get("client_tid", 0) <= 65535 or not 1 <= result.get("transfer_tid", 0) <= 65535
            or result["transfer_tid"] == 69):
        raise GateFailure("server_tid_contract")
    counts = result.get("counts", {})
    blocks = block_count(payload.expected_bytes)
    if (set(counts) != set(_COUNTERS) or counts["blocks_acked"] != blocks
            or counts["payload_bytes_acked"] != payload.expected_bytes
            or counts["data_packets_sent"] < blocks
            or counts["data_bytes_sent_including_retries"] < payload.expected_bytes
            or counts["retransmissions"] != counts["data_packets_sent"] - blocks):
        raise GateFailure("server_count_contract")


def run_ram_gate(*, channel, server, payload: VerifiedPayload, server_ipv4, client_ipv4,
                 guard, network_authorized: bool, clock=time.monotonic) -> dict:
    """Core only. `guard()` must return True before every command/server start.

    `channel.command(command, timeout)` must return only that fresh response.
    Its prompt is acquired externally. `server.close()` must confirm True and
    contain any partially started helper even when start/finish raised.
    """
    started = clock()
    result = {"schema": SCHEMA, "status": FAIL, "candidate_sha256": None, "candidate_bytes": None,
              "candidate_crc32": None, "address": ADDRESS, "server_closed": False, "server_result": None,
              "flash_writes": 0, "environment_saved": False, "runtime_adapters_verified": False,
              "implementation_scope": "protocol core; physical adapters and execution review pending",
              "generated_at_utc": datetime.now(timezone.utc).isoformat(), "tx_commands_issued": 0,
              "tftp_commands_issued": 0, "checks": {}}
    stage = "authorization"
    server_attempted = False
    completed = False

    def guarded() -> None:
        if guard() is not True:
            raise GateFailure("guard_not_confirmed")

    def command(text: str, timeout: float, *, deadline: float | None = None) -> bytes:
        guarded()
        if deadline is not None:
            timeout = min(timeout, deadline - clock())
            if timeout <= 0:
                raise GateFailure("server_lifetime_expired")
        began = clock()
        result["tx_commands_issued"] += 1
        if text.startswith("tftpboot "):
            result["tftp_commands_issued"] += 1
        response = channel.command(text, timeout)
        if clock() - began > timeout:
            raise GateFailure("channel_timeout_contract")
        return response

    try:
        if type(network_authorized) is not bool or network_authorized is not True:
            raise GateFailure("network_authorization_required")
        stage = "preflight"
        pin = validate_payload(payload)
        server_ipv4 = exact_ipv4(server_ipv4)
        server_address = ipaddress.IPv4Address(server_ipv4)
        local_subnet = ipaddress.IPv4Network("192.168.1.0/24")
        if (client_ipv4 != CLIENT_IPV4 or not isinstance(client_ipv4, str)
                or server_address not in local_subnet or server_ipv4 == client_ipv4
                or server_address in {local_subnet.network_address, local_subnet.broadcast_address}):
            raise GateFailure("network_scope")
        result.update(candidate_sha256=pin.sha256, candidate_bytes=pin.byte_count)
        for variable, value in (("ipaddr", client_ipv4), ("serverip", server_ipv4)):
            stage = "setenv_" + variable
            text = f"setenv {variable} {value}"
            verify_silent(command(text, 30), text)
        for variable, value in (("ipaddr", client_ipv4), ("serverip", server_ipv4)):
            stage = "readback_" + variable
            text = "printenv " + variable
            verify_environment(command(text, 30), text, variable, value)
        result["checks"]["volatile_network_environment"] = True
        stage = "server_start"
        guarded()
        server_began = clock()
        server_attempted = True
        ready = server.start(payload, bind=server_ipv4, client=client_ipv4,
                             filename=pin.source_path.name, timeout=SERVER_TIMEOUT)
        verify_ready(ready, payload, server_ipv4, client_ipv4)
        result["checks"]["server_ready"] = True
        stage = "tftpboot"
        text = f"tftpboot {ADDRESS} {pin.source_path.name}"
        verify_transfer(command(text, SERVER_TIMEOUT, deadline=server_began + SERVER_TIMEOUT), text, pin.byte_count)
        result["checks"]["decimal_and_hex_transfer_count"] = True
        stage = "server_finish"
        finished = clock()
        raw_server_result = server.finish(timeout=10)
        if clock() - finished > 10:
            raise GateFailure("server_finish_timeout")
        result["server_result"] = sanitize_server_result(raw_server_result, payload, server_ipv4, client_ipv4)
        verify_server_result(result["server_result"], payload, server_ipv4, client_ipv4)
        result["checks"]["scoped_server_transfer"] = True
        stage = "filesize"
        text = "printenv filesize"
        verify_filesize(command(text, 30), text, pin.byte_count)
        result["checks"]["filesize"] = True
        stage = "iminfo"
        text = f"iminfo {ADDRESS}"
        verify_iminfo(command(text, 90), text)
        result["checks"]["iminfo"] = True
        stage = "crc32"
        text = f"crc32 {ADDRESS} 0x{pin.byte_count:08x} {CRC_ADDRESS}; md.l {CRC_ADDRESS} 1"
        result["candidate_crc32"] = verify_crc(command(text, 120), text, pin)
        result["checks"]["ram_crc32"] = True
        completed = True
    except Exception as error:
        result["failed_stage"] = stage
        result["error_code"] = error.code if type(error) is GateFailure else "adapter_or_input_error"
        result["error_type"] = type(error).__name__
    finally:
        if server_attempted:
            try:
                result["server_closed"] = server.close() is True
            except Exception:
                result["server_closed"] = False
            if not result["server_closed"]:
                result["cleanup_error"] = "server_close_unconfirmed"
        result["elapsed_seconds"] = round(clock() - started, 6)
    if completed and result["server_closed"]:
        result["status"] = PASS
    return result
