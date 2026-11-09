"""File-only binding for reuse of one already granted Windows UDP permission."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
PERMISSION = ROOT / "outputs/authorizations/f334-executor-20260921T111605Z/permission.json"
PERMISSION_SHA = "4c92fd4156139a0985d8aed2c913e11c91b6c04aef3b35a326aa3efc6ec8bb21"
FINGERPRINT = "df0c7fac07a2dfae253bd0cef8f4b9a76e8b46b6965ba635be6831ccbbd8270f"
PROGRAM = r"/workspace/user-home\AppData\Local\Programs\Python\Python312\python.exe"
PROGRAM_SHA = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
RULE = r"UDP Query User{B53A0DF9-DAAE-4615-9572-87C57A3EF67B}/workspace/user-home\appdata\local\programs\python\python312\python.exe"
PROBE = ROOT / "outputs/preflight/f326-existing-tftp-probe-20260921T102246Z/result.json"
PROBE_SHA = "b09b2bd92c098c0a0833453a4c29670bcc08c7c7c14b4db506dc130281c6edbf"


def validate_transfer_probe() -> dict:
    data = PROBE.read_bytes()
    if hashlib.sha256(data).hexdigest() != PROBE_SHA:
        raise ValueError("existing-permission transfer probe changed")
    probe = json.loads(data)
    server = probe.get("server_result", {})
    if (probe.get("status") != "PASS_TFTP_WITH_EXISTING_PERMISSION"
        or type(probe.get("client_returncode")) is not int or probe["client_returncode"] != 0
        or probe.get("client_stdout") != "PASS_TFTP_SYNTHETIC bytes=4096 data_blocks=9\n"
        or probe.get("client_stderr") != "" or probe.get("python_sha256") != PROGRAM_SHA
        or probe.get("permission_before") != probe.get("permission_after")
        or any(probe.get(key) is not True for key in ("permission_unchanged", "server_thread_exited", "ram_client_removed"))
        or any(probe.get(key) is not False for key in ("firewall_changes", "firmware_transfer", "flash", "uart", "reboot", "radio_changes"))
        or server.get("status") != "PASS_TFTP_SINGLE_TRANSFER" or server.get("sockets_closed") is not True
        or server.get("bind") != "192.168.1.49" or server.get("allow_client") != "192.168.1.90"
        or server.get("file", {}).get("bytes") != 4096 or server.get("transfer_complete") is not True):
        raise ValueError("existing-permission probe does not prove the expected bounded transport")
    return {"path": str(PROBE), "sha256": PROBE_SHA}


def projection_fingerprint(projection: dict) -> str:
    if not isinstance(projection, dict) or not projection or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in projection.items()
    ):
        raise ValueError("permission projection must contain only string fields")
    canonical = "\n".join(key + "=" + base64.b64encode(projection[key].encode("utf-8")).decode("ascii")
                          for key in sorted(projection))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_permission(path: Path, expected_sha: str, *, python_executable: str) -> dict:
    if expected_sha != PERMISSION_SHA:
        raise ValueError("exact existing-permission record required")
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 32768:
        raise ValueError("bounded regular permission record required")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PERMISSION_SHA:
        raise ValueError("existing-permission record hash changed")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate permission key")
            result[key] = value
        return result
    record = json.loads(data, object_pairs_hook=unique)
    expected = {"schema": "openmitrastar.f326-existing-firewall-permission/v1",
                "mode": "existing-permission", "target_host": "192.168.1.90",
                "target_model": "HGW-500BNA-QCv2 A2", "server_ipv4": "192.168.1.49",
                "interface_index": 18, "interface_alias": "Ethernet",
                "candidate_sha256": "e18b221dda9a61bd1066c155c0cd7b44aef0d0fe06b1a1752a7e759e7730c7ec",
                "candidate_bytes": 5332992,
                "restore_sha256": "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18",
                "network_authorization_sha256": "3e36ac59c12a0ef61d6a0e564be072a91d23b62c98ec28696d5ac2956b32c572",
                "rule_name": RULE, "fingerprint_sha256": FINGERPRINT}
    if not isinstance(record, dict) or any(type(record.get(key)) is not type(value) or record.get(key) != value
                                           for key, value in expected.items()):
        raise ValueError("existing-permission scope mismatch")
    if record.get("authorized") is not True or any(record.get(key) is not False for key in (
        "firewall_changes_allowed", "existing_rule_owned_by_executor", "require_administrator",
        "privilege_request_allowed", "automatic_permission_fallback_allowed",
        "host_address_or_route_changes_allowed", "boot_environment_persistence_allowed"
    )):
        raise ValueError("existing-permission record allows an unreviewed effect")
    projection = record["projection"]
    if projection_fingerprint(projection) != FINGERPRINT or projection.get("program_sha256") != PROGRAM_SHA:
        raise ValueError("existing-permission fingerprint/program identity changed")
    if PureWindowsPath(python_executable) != PureWindowsPath(PROGRAM):
        raise ValueError("existing permission requires exact Python312 interpreter")
    return {"path": str(path.resolve()), "sha256": PERMISSION_SHA, "fingerprint_sha256": FINGERPRINT,
            "rule_name": RULE, "python_executable": PROGRAM, "program_sha256": PROGRAM_SHA,
            "projection": projection, "firewall_changes_allowed": False,
            "require_administrator": False, "fallback_allowed": False,
            "transport_probe": validate_transfer_probe()}
