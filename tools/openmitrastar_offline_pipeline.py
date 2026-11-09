#!/usr/bin/env python3
"""Deterministic, offline-only OpenMitraStar Linux 5.10 build pipeline.

The pipeline deliberately has no router, UART, TFTP, SSH, HTTP, deployment, or
flash stage.  It only inventories pinned local inputs, checks the existing WSL
build environment, optionally runs the cache-preserving RAMSSH builder, and
writes an auditable manifest/report.

Every produced Linux 5.10 image remains RAM-ONLY/NO-GO.  This program never
promotes an artifact to a flash candidate.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
OEM_NAME = (
    "Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_"
    "mitrastar_webformat.bin"
)
OEM_PATH = ROOT / OEM_NAME
OEM_EXPECTED_SIZE = 6_729_728
OEM_EXPECTED_SHA256 = (
    "f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f"
)
SOURCE_DATE_EPOCH = 1_785_024_000
RAMSSH_BASE = "linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO"
KERNEL_OUTPUT = ROOT / "outputs" / "kernel-port"
DEFAULT_OUTPUT = ROOT / "outputs" / "offline-pipeline"

BUILD_SCRIPTS = (
    ROOT / "tools" / "build_topaz_linux_510_fast.sh",
    ROOT / "tools" / "build_topaz_linux_510.sh",
    ROOT / "tools" / "apply_topaz_linux_510_overlay.sh",
    ROOT / "work" / "ssh-emulation" / "build-ramssh-rootfs.sh",
)

INPUT_ROOTS = (
    ROOT / "work" / "kernel-port" / "linux-5.10",
    ROOT / "work" / "kernel-port" / "configs",
    ROOT / "work" / "kernel-port" / "initramfs",
)

FIXED_INPUTS = BUILD_SCRIPTS + (
    Path(__file__).resolve(),
    ROOT / "tools" / "prepare_openmitrastar_build_env.ps1",
    ROOT / "tools" / "bootbase_contract_emulator.py",
    ROOT
    / "work"
    / "toolchains"
    / "arc-uclibc"
    / "arc-arc700-linux-uclibc"
    / "bin"
    / "arc-linux-gcc",
)

REQUIRED_RAMSSH = {
    "config": KERNEL_OUTPUT / f"{RAMSSH_BASE}.config",
    "vmlinux": KERNEL_OUTPUT / f"{RAMSSH_BASE}.vmlinux",
    "uimage": KERNEL_OUTPUT / f"{RAMSSH_BASE}.uImage",
    "initramfs": KERNEL_OUTPUT / f"{RAMSSH_BASE}.initramfs.cpio",
    "client_public_key": KERNEL_OUTPUT / f"{RAMSSH_BASE}.client_ed25519.pub",
    "sha256_manifest": KERNEL_OUTPUT / f"{RAMSSH_BASE}.sha256",
}

# This is a defence-in-depth static gate for the exact scripts invoked by the
# pipeline.  It is intentionally conservative.  It is not presented as an OS
# network sandbox; the stronger guarantee is that the only executable build
# entrypoint is an allow-listed, locally hashed script.
FORBIDDEN_BUILD_PATTERNS = {
    "curl": re.compile(r"(?i)(?<![\w-])curl(?:\s|$)"),
    "wget": re.compile(r"(?i)(?<![\w-])wget(?:\s|$)"),
    "remote-url": re.compile(r"(?i)https?://"),
    "git-network": re.compile(r"(?i)\bgit\s+(?:clone|fetch|pull)\b"),
    "powershell-web": re.compile(
        r"(?i)\b(?:Invoke-WebRequest|Invoke-RestMethod|Start-BitsTransfer)\b"
    ),
    "file-transfer": re.compile(
        r"(?i)(?<![\w-])(?:tftp|ftp|scp|sftp|netcat|nc)(?:\s|$)"
    ),
    "shell-socket": re.compile(r"/dev/(?:tcp|udp)/"),
}


class PipelineError(RuntimeError):
    """Expected pipeline failure with a user-actionable message."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    st = path.stat()
    record: dict[str, Any] = {
        "path": rel(path),
        "size": st.st_size,
        "sha256": sha256_file(path),
    }
    if path.is_symlink():
        record["symlink_target"] = os.readlink(path)
    return record


def canonical_fingerprint(records: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: item["path"]):
        line = f"{record['path']}\0{record['size']}\0{record['sha256']}\n"
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def decode_process_output(raw: bytes) -> str:
    if b"\0" in raw:
        return raw.decode("utf-16-le", errors="replace").replace("\0", "")
    return raw.decode("utf-8", errors="replace")


def run_command(command: list[str], cwd: Path = ROOT) -> tuple[int, str]:
    process = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return process.returncode, decode_process_output(process.stdout)


def windows_to_wsl(path: Path) -> str:
    resolved = str(path.resolve())
    match = re.match(r"^(?P<drive>[A-Za-z]):\\(?P<rest>.*)$", resolved)
    if not match:
        raise PipelineError(f"unsupported Windows path for WSL: {resolved}")
    drive = match.group("drive").lower()
    rest = match.group("rest").replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    status: str,
    detail: str,
) -> None:
    checks.append({"id": check_id, "status": status, "detail": detail})


def scan_build_policy() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in BUILD_SCRIPTS:
        if not path.is_file():
            findings.append(
                {"path": rel(path), "line": None, "rule": "missing-build-script"}
            )
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for rule, pattern in FORBIDDEN_BUILD_PATTERNS.items():
                if pattern.search(line):
                    findings.append(
                        {
                            "path": rel(path),
                            "line": line_number,
                            "rule": rule,
                            "text": line.strip()[:240],
                        }
                    )
    return findings


def collect_inputs() -> tuple[list[dict[str, Any]], list[str]]:
    paths: set[Path] = set(FIXED_INPUTS)
    missing: list[str] = []
    for root in INPUT_ROOTS:
        if not root.is_dir():
            missing.append(rel(root))
            continue
        paths.update(item for item in root.rglob("*") if item.is_file())

    records: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda item: rel(item)):
        if not path.is_file():
            missing.append(rel(path))
            continue
        try:
            records.append(file_record(path))
        except OSError as exc:
            missing.append(f"{rel(path)} ({exc})")
    return records, sorted(set(missing))


def oem_record() -> dict[str, Any]:
    if not OEM_PATH.is_file():
        raise PipelineError(f"missing immutable OEM source: {OEM_PATH}")
    record = file_record(OEM_PATH)
    attributes = getattr(OEM_PATH.stat(), "st_file_attributes", 0)
    record.update(
        {
            "expected_size": OEM_EXPECTED_SIZE,
            "expected_sha256": OEM_EXPECTED_SHA256,
            "size_matches": record["size"] == OEM_EXPECTED_SIZE,
            "sha256_matches": record["sha256"] == OEM_EXPECTED_SHA256,
            "windows_read_only": bool(attributes & stat.FILE_ATTRIBUTE_READONLY),
            "immutable_policy": "read-only pinned input; never an output path",
        }
    )
    return record


def wsl_base_command(distro: str, user: str) -> list[str]:
    return ["wsl.exe", "-d", distro, "-u", user, "--"]


def list_wsl_distros() -> tuple[int, list[str], str]:
    if shutil.which("wsl.exe") is None:
        return 127, [], "wsl.exe not found"
    rc, output = run_command(["wsl.exe", "--list", "--quiet"])
    distros = [line.strip().lstrip("*").strip() for line in output.splitlines()]
    return rc, [item for item in distros if item], output


def wsl_probe(
    distro: str,
    user: str,
    kernel_source: str,
    build_root: str,
) -> tuple[int, str]:
    project = windows_to_wsl(ROOT)
    toolchain = (
        f"{project}/work/toolchains/arc-uclibc/"
        "arc-arc700-linux-uclibc/bin/arc-linux-"
    )
    script = r"""
set -eu
fail() {
    printf 'CHECK_FAIL=%s\n' "$1" >&2
    exit 20
}
test -d "$OM_PROJECT"
test -f "$OM_PROJECT/tools/build_topaz_linux_510_fast.sh"
test -f "$OM_SOURCE/Makefile"
test -d "$OM_OUTPUT"
test -w "$OM_OUTPUT"
test -x "${OM_TOOLCHAIN}gcc"
command -v sh >/dev/null
command -v make >/dev/null
command -v sha256sum >/dev/null
command -v base64 >/dev/null
printf 'WSL_DISTRO=%s\n' "${WSL_DISTRO_NAME:-unknown}"
printf 'WSL_USER=%s\n' "$(id -un)"
printf 'KERNEL_SOURCE=%s\n' "$OM_SOURCE"
printf 'BUILD_ROOT=%s\n' "$OM_OUTPUT"
printf 'TOOLCHAIN=%s\n' "$("${OM_TOOLCHAIN}gcc" --version | sed -n '1p')"
printf 'MAKE=%s\n' "$(make --version | sed -n '1p')"
printf 'KERNEL_MAKEFILE_SHA256=%s\n' "$(sha256sum "$OM_SOURCE/Makefile" | cut -d ' ' -f 1)"
for dependency in \
    /home/user/openmitrastar-ssh-lab/busybox-1.38.0/busybox \
    /home/user/openmitrastar-ssh-lab/dropbear-arc-multiuser-noatomic/dropbearmulti \
    /home/user/openmitrastar-ssh-lab/dropbear-native/dropbearkey \
    /home/user/openmitrastar-ramssh-keys/client_ed25519.pub \
    /home/user/openmitrastar-ramssh-keys/dropbear_ed25519_host_key; do
    test -f "$dependency" || fail "dependency:$dependency"
    printf 'DEPENDENCY_SHA256=%s:%s\n' \
        "$dependency" "$(sha256sum "$dependency" | cut -d ' ' -f 1)"
done
""".strip()
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    bootstrap = f"printf '%s' '{encoded}' | base64 -d | sh"
    command = wsl_base_command(distro, user) + [
        "env",
        f"OM_PROJECT={project}",
        f"OM_SOURCE={kernel_source}",
        f"OM_OUTPUT={build_root}",
        f"OM_TOOLCHAIN={toolchain}",
        "sh",
        "-c",
        bootstrap,
    ]
    return run_command(command)


def cache_probe(
    distro: str,
    user: str,
    kernel_source: str,
    build_root: str,
) -> tuple[int, str]:
    project = windows_to_wsl(ROOT)
    command = wsl_base_command(distro, user) + [
        "env",
        f"TOPAZ_KERNEL_SRC={kernel_source}",
        f"TOPAZ_BUILD_ROOT={build_root}",
        "TOPAZ_PACK_FLASH_ARTIFACTS=0",
        "sh",
        f"{project}/tools/build_topaz_linux_510_fast.sh",
        "--check",
    ]
    return run_command(command)


def read_config_features() -> dict[str, int]:
    config_path = REQUIRED_RAMSSH["config"]
    text = config_path.read_text(encoding="utf-8", errors="replace") if config_path.exists() else ""

    def enabled(symbol: str, default: int = 0) -> int:
        if re.search(rf"(?m)^{re.escape(symbol)}=y$", text):
            return 1
        if re.search(rf"(?m)^# {re.escape(symbol)} is not set$", text):
            return 0
        return default

    return {
        "TOPAZ_HEAD_WDT": enabled("CONFIG_QTN_TOPAZ_HEAD_WDT_CANARY"),
        "TOPAZ_BOOT_TRACE": enabled("CONFIG_OPENMITRASTAR_BOOT_TRACE"),
        "TOPAZ_MMU_ENTRY_PROBE": enabled("CONFIG_OPENMITRASTAR_MMU_ENTRY_PROBE"),
    }


def run_incremental_build(
    distro: str,
    user: str,
    kernel_source: str,
    build_root: str,
    jobs: int,
    features: dict[str, int],
) -> tuple[int, str, list[str]]:
    project = windows_to_wsl(ROOT)
    environment = [
        f"TOPAZ_KERNEL_SRC={kernel_source}",
        f"TOPAZ_BUILD_ROOT={build_root}",
        f"TOPAZ_JOBS={jobs}",
        "TOPAZ_INCREMENTAL=1",
        "TOPAZ_PACK_FLASH_ARTIFACTS=0",
        f"SOURCE_DATE_EPOCH={SOURCE_DATE_EPOCH}",
        *(f"{key}={value}" for key, value in sorted(features.items())),
    ]
    command = wsl_base_command(distro, user) + [
        "env",
        *environment,
        "sh",
        f"{project}/tools/build_topaz_linux_510_fast.sh",
        "ramssh",
    ]
    rc, output = run_command(command)
    printable = ["wsl.exe", "-d", distro, "-u", user, "--", "env", *environment]
    printable.extend(["sh", f"{project}/tools/build_topaz_linux_510_fast.sh", "ramssh"])
    return rc, output, printable


def parse_uimage(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    errors: list[str] = []
    if len(raw) < 64:
        return {"valid": False, "errors": ["image shorter than 64-byte uImage header"]}
    fields = struct.unpack(">7I4B32s", raw[:64])
    magic, hcrc, timestamp, payload_size, load, entry, dcrc = fields[:7]
    os_id, arch, image_type, compression, name_raw = fields[7:]
    header = bytearray(raw[:64])
    header[4:8] = b"\0\0\0\0"
    calculated_hcrc = binascii.crc32(header) & 0xFFFFFFFF
    payload = raw[64 : 64 + payload_size]
    calculated_dcrc = binascii.crc32(payload) & 0xFFFFFFFF
    if magic != 0x27051956:
        errors.append(f"bad magic 0x{magic:08x}")
    if calculated_hcrc != hcrc:
        errors.append(
            f"bad header CRC stored=0x{hcrc:08x} calculated=0x{calculated_hcrc:08x}"
        )
    if len(payload) != payload_size:
        errors.append(f"payload truncated: expected {payload_size}, got {len(payload)}")
    if calculated_dcrc != dcrc:
        errors.append(
            f"bad data CRC stored=0x{dcrc:08x} calculated=0x{calculated_dcrc:08x}"
        )
    if len(raw) != 64 + payload_size:
        errors.append(
            f"unexpected trailing/short data: file={len(raw)} expected={64 + payload_size}"
        )
    return {
        "valid": not errors,
        "errors": errors,
        "magic": f"0x{magic:08x}",
        "header_crc": f"0x{hcrc:08x}",
        "calculated_header_crc": f"0x{calculated_hcrc:08x}",
        "timestamp": timestamp,
        "payload_size": payload_size,
        "load": f"0x{load:08x}",
        "entry": f"0x{entry:08x}",
        "data_crc": f"0x{dcrc:08x}",
        "calculated_data_crc": f"0x{calculated_dcrc:08x}",
        "os": os_id,
        "arch": arch,
        "type": image_type,
        "compression": compression,
        "name": name_raw.split(b"\0", 1)[0].decode("ascii", errors="replace"),
    }


def verify_sha_manifest(path: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return {"valid": False, "entries": [], "errors": ["manifest missing"]}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            errors.append(f"malformed line {line_number}")
            continue
        expected, listed_path = parts
        candidate = KERNEL_OUTPUT / Path(listed_path.strip()).name
        if not candidate.is_file():
            errors.append(f"missing listed artifact: {candidate.name}")
            continue
        actual = sha256_file(candidate)
        matches = actual.lower() == expected.lower()
        if not matches:
            errors.append(f"hash mismatch: {candidate.name}")
        entries.append(
            {
                "path": rel(candidate),
                "expected_sha256": expected.lower(),
                "actual_sha256": actual,
                "matches": matches,
            }
        )
    return {"valid": bool(entries) and not errors, "entries": entries, "errors": errors}


def artifact_class(path: Path) -> str:
    lowered = path.name.lower()
    full = rel(path).lower()
    if any(token in lowered for token in ("no-go", "ram-only", "no-flash")):
        return "blocked-no-go"
    if "experiments-no-go" in full:
        return "blocked-no-go"
    if lowered.endswith("contract.json"):
        return "offline-contract-evidence"
    if lowered == "manifest.json" and full.startswith("versions/"):
        return "legacy-version-manifest"
    if lowered.endswith((".log", ".txt", ".md", ".json", ".sha256")):
        return "evidence"
    return "unpromoted-artifact"


def collect_artifact_inventory() -> list[dict[str, Any]]:
    paths: set[Path] = {path for path in REQUIRED_RAMSSH.values() if path.is_file()}
    paths.update(KERNEL_OUTPUT.glob("linux510-*-contract.json"))
    paths.update(KERNEL_OUTPUT.glob("linux510-ramssh-live-state-*.txt"))
    for evidence in (
        KERNEL_OUTPUT / "radiohw-probe" / "SHA256SUMS",
        KERNEL_OUTPUT / "quantenna-linux510" / "SHA256SUMS",
        KERNEL_OUTPUT / "realtek-rtl8192ee-linux510" / "SHA256SUMS",
    ):
        if evidence.is_file():
            paths.add(evidence)
    paths.update((ROOT / "versions").glob("*/build/manifest.json"))

    inventory: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda item: rel(item)):
        record = file_record(path)
        record.update(
            {
                "classification": artifact_class(path),
                "candidate_eligible": False,
                "promotion_reason": "offline pipeline never promotes flash candidates",
            }
        )
        inventory.append(record)
    return inventory


def validate_ramssh(mode: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    missing = [name for name, path in REQUIRED_RAMSSH.items() if not path.is_file()]
    if missing:
        status = "FAIL" if mode == "build" else "WARN"
        add_check(
            checks,
            "ramssh-artifacts",
            status,
            "missing: " + ", ".join(missing),
        )
        return {"present": False, "missing": missing}, checks

    add_check(checks, "ramssh-artifacts", "PASS", "all required artifacts present")
    uimage = parse_uimage(REQUIRED_RAMSSH["uimage"])
    add_check(
        checks,
        "ramssh-uimage-crc",
        "PASS" if uimage["valid"] else "FAIL",
        "header and payload CRC valid" if uimage["valid"] else "; ".join(uimage["errors"]),
    )

    sha_manifest = verify_sha_manifest(REQUIRED_RAMSSH["sha256_manifest"])
    add_check(
        checks,
        "ramssh-sha256-manifest",
        "PASS" if sha_manifest["valid"] else "FAIL",
        "all listed hashes match"
        if sha_manifest["valid"]
        else "; ".join(sha_manifest["errors"]),
    )

    config_text = REQUIRED_RAMSSH["config"].read_text(
        encoding="utf-8", errors="replace"
    )
    config_requirements = {
        "ramssh-localversion": 'CONFIG_LOCALVERSION="-openmitrastar-ramssh"',
        "block-disabled": "# CONFIG_BLOCK is not set",
        "mtd-disabled": "# CONFIG_MTD is not set",
        "topaz-emac": "CONFIG_QTN_TOPAZ_EMAC=y",
    }
    config_contract: dict[str, bool] = {}
    for name, needle in config_requirements.items():
        matched = needle in config_text
        config_contract[name] = matched
        add_check(
            checks,
            f"config-{name}",
            "PASS" if matched else "FAIL",
            needle,
        )

    init_magic = REQUIRED_RAMSSH["initramfs"].read_bytes()[:6]
    init_valid = init_magic == b"070701"
    add_check(
        checks,
        "ramssh-initramfs-newc",
        "PASS" if init_valid else "FAIL",
        "newc cpio magic present" if init_valid else f"unexpected magic {init_magic!r}",
    )

    key_text = REQUIRED_RAMSSH["client_public_key"].read_text(
        encoding="utf-8", errors="replace"
    )
    key_valid = key_text.startswith("ssh-ed25519 ") or key_text.startswith("ssh-rsa ")
    add_check(
        checks,
        "ramssh-public-key",
        "PASS" if key_valid else "FAIL",
        "public key only; no private key inventoried" if key_valid else "unexpected key format",
    )

    name_guard = all(
        "RAM-ONLY-NO-GO" in path.name
        for name, path in REQUIRED_RAMSSH.items()
        if name != "sha256_manifest"
    ) and "RAM-ONLY-NO-GO" in REQUIRED_RAMSSH["sha256_manifest"].name
    add_check(
        checks,
        "no-go-name-guard",
        "PASS" if name_guard else "FAIL",
        "all RAMSSH products retain RAM-ONLY-NO-GO naming",
    )

    return (
        {
            "present": True,
            "uimage": uimage,
            "sha256_manifest": sha_manifest,
            "config_contract": config_contract,
            "initramfs_newc": init_valid,
            "public_key_only": key_valid,
            "candidate_eligible": False,
            "classification": "RAM-ONLY-NO-GO",
        },
        checks,
    )


def markdown_report(manifest: dict[str, Any]) -> str:
    checks = manifest["checks"]
    lines = [
        "# OpenMitraStar Linux 5.10 offline pipeline",
        "",
        f"- Resultado: **{manifest['result']}**",
        f"- Modo: `{manifest['mode']}`",
        f"- Generado: `{manifest['generated_at_utc']}`",
        f"- Fingerprint de entradas: `{manifest['inputs']['fingerprint_sha256']}`",
        f"- Bin OEM: `{manifest['oem_source']['sha256']}`",
        "- Acceso a router/red/flash: **no ejecutado y no implementado**",
        "- Candidatos promovidos: **0**",
        "",
        "## Comprobaciones",
        "",
        "| Check | Estado | Detalle |",
        "|---|---:|---|",
    ]
    for check in checks:
        detail = str(check["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{check['id']}` | {check['status']} | {detail} |")
    lines.extend(
        [
            "",
            "## Build",
            "",
            f"- Ejecutado: `{manifest['build']['executed']}`",
            f"- Caché incremental: `{manifest['build']['cache_policy']}`",
            f"- SOURCE_DATE_EPOCH: `{manifest['build']['source_date_epoch']}`",
            "- Salida Linux 5.10: permanece `RAM-ONLY-NO-GO`; no es firmware flasheable.",
            "",
            "## Artefactos",
            "",
            f"Se inventariaron `{len(manifest['artifacts']['items'])}` artefactos/evidencias. ",
            "Todos tienen `candidate_eligible=false`.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preflight/build/validate OpenMitraStar Linux 5.10 offline"
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("preflight", "build", "validate"),
        default="preflight",
        help="preflight is the safe dry-run; build uses the existing incremental cache",
    )
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--wsl-user", default="root")
    parser.add_argument(
        "--kernel-source", default="/home/user/mitrastar-linux-5.10.260"
    )
    parser.add_argument("--build-root", default="/home/user/openmitrastar-build")
    parser.add_argument("--jobs", type=int, default=12)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.jobs < 1:
        raise SystemExit("--jobs must be greater than zero")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    generated_at = utc_now()

    try:
        oem_before = oem_record()
    except PipelineError as exc:
        oem_before = {"path": rel(OEM_PATH), "error": str(exc)}
        add_check(checks, "oem-source", "FAIL", str(exc))
    else:
        oem_valid = bool(
            oem_before["size_matches"]
            and oem_before["sha256_matches"]
            and oem_before["windows_read_only"]
        )
        add_check(
            checks,
            "oem-source",
            "PASS" if oem_valid else "FAIL",
            "size/hash pinned and Windows read-only"
            if oem_valid
            else "OEM source size/hash/readonly policy mismatch",
        )

    inputs, missing_inputs = collect_inputs()
    input_fingerprint_before = canonical_fingerprint(inputs) if inputs else None
    add_check(
        checks,
        "build-inputs",
        "PASS" if not missing_inputs else "FAIL",
        f"{len(inputs)} hashed local inputs"
        if not missing_inputs
        else "missing: " + ", ".join(missing_inputs),
    )

    policy_findings = scan_build_policy()
    add_check(
        checks,
        "offline-build-policy",
        "PASS" if not policy_findings else "FAIL",
        "allow-listed build path contains no network/transfer commands"
        if not policy_findings
        else f"{len(policy_findings)} forbidden command/reference finding(s)",
    )

    distro_rc, distros, distro_output = list_wsl_distros()
    distro_ok = distro_rc == 0 and args.distro in distros
    add_check(
        checks,
        "wsl-distro",
        "PASS" if distro_ok else "FAIL",
        f"{args.distro} installed" if distro_ok else f"available={distros!r}",
    )

    probe_rc, probe_output = (127, "WSL probe skipped")
    cache_rc, cache_output = (127, "cache probe skipped")
    if distro_ok:
        probe_rc, probe_output = wsl_probe(
            args.distro, args.wsl_user, args.kernel_source, args.build_root
        )
        add_check(
            checks,
            "wsl-build-environment",
            "PASS" if probe_rc == 0 else "FAIL",
            probe_output.strip()[-1000:] if probe_output.strip() else f"exit={probe_rc}",
        )
        if probe_rc == 0:
            cache_rc, cache_output = cache_probe(
                args.distro, args.wsl_user, args.kernel_source, args.build_root
            )
            add_check(
                checks,
                "incremental-cache",
                "PASS" if cache_rc == 0 else "FAIL",
                cache_output.strip()[-1000:]
                if cache_output.strip()
                else f"exit={cache_rc}",
            )

    features = read_config_features()
    build_info: dict[str, Any] = {
        "executed": False,
        "exit_code": None,
        "command": None,
        "cache_policy": "preserve existing RAMSSH state; bootstrap only if absent",
        "flash_packaging": False,
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "jobs": args.jobs,
        "preserved_features": features,
        "log": None,
    }

    lock_dir = output_dir / ".build.lock"
    if args.mode == "build":
        prerequisites_failed = any(
            check["status"] == "FAIL"
            for check in checks
            if check["id"]
            in {
                "oem-source",
                "build-inputs",
                "offline-build-policy",
                "wsl-distro",
                "wsl-build-environment",
                "incremental-cache",
            }
        )
        if prerequisites_failed:
            add_check(
                checks,
                "build-execution",
                "FAIL",
                "build refused because an offline preflight prerequisite failed",
            )
        else:
            try:
                lock_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                add_check(
                    checks,
                    "build-execution",
                    "FAIL",
                    f"another offline build owns {rel(lock_dir)}",
                )
            else:
                try:
                    build_rc, build_output, printable = run_incremental_build(
                        args.distro,
                        args.wsl_user,
                        args.kernel_source,
                        args.build_root,
                        args.jobs,
                        features,
                    )
                    build_log = output_dir / "build.log"
                    atomic_write(build_log, build_output)
                    build_info.update(
                        {
                            "executed": True,
                            "exit_code": build_rc,
                            "command": printable,
                            "log": rel(build_log),
                        }
                    )
                    add_check(
                        checks,
                        "build-execution",
                        "PASS" if build_rc == 0 else "FAIL",
                        f"incremental RAMSSH builder exit={build_rc}; log={rel(build_log)}",
                    )
                finally:
                    lock_dir.rmdir()

    try:
        oem_after = oem_record()
    except PipelineError as exc:
        oem_after = {"error": str(exc)}
        add_check(checks, "oem-post-build", "FAIL", str(exc))
    else:
        unchanged = (
            oem_before.get("sha256") == oem_after.get("sha256")
            and oem_before.get("size") == oem_after.get("size")
        )
        add_check(
            checks,
            "oem-post-build",
            "PASS" if unchanged else "FAIL",
            "immutable OEM source unchanged",
        )

    inputs_after, missing_inputs_after = collect_inputs()
    input_fingerprint_after = (
        canonical_fingerprint(inputs_after) if inputs_after else None
    )
    input_snapshot_stable = (
        input_fingerprint_before == input_fingerprint_after
        and missing_inputs == missing_inputs_after
    )
    add_check(
        checks,
        "input-snapshot-stability",
        "PASS" if input_snapshot_stable else "FAIL",
        "build inputs unchanged during pipeline run"
        if input_snapshot_stable
        else "build inputs changed concurrently; rerun from a stable snapshot",
    )

    ramssh_validation, validation_checks = validate_ramssh(args.mode)
    checks.extend(validation_checks)
    artifacts = collect_artifact_inventory()
    artifact_fingerprint = canonical_fingerprint(artifacts) if artifacts else None

    add_check(
        checks,
        "candidate-promotion",
        "PASS",
        "zero promoted candidates; all inventory items candidate_eligible=false",
    )
    add_check(
        checks,
        "hardware-side-effects",
        "PASS",
        "router/network/UART/TFTP/SSH/flash actions are absent from this pipeline",
    )

    failed = [check for check in checks if check["status"] == "FAIL"]
    manifest: dict[str, Any] = {
        "schema": "openmitrastar.offline-pipeline/v1",
        "generated_at_utc": generated_at,
        "mode": args.mode,
        "result": "PASS" if not failed else "BLOCKED",
        "safety": {
            "offline_only": True,
            "router_accessed": False,
            "network_actions": [],
            "uart_actions": [],
            "tftp_actions": [],
            "flash_actions": [],
            "promoted_candidates": [],
            "no_go_artifacts_are_candidates": False,
        },
        "oem_source": oem_after,
        "inputs": {
            "items": inputs_after,
            "missing": missing_inputs_after,
            "fingerprint_sha256": input_fingerprint_after,
            "pre_run_fingerprint_sha256": input_fingerprint_before,
            "stable_during_run": input_snapshot_stable,
        },
        "offline_policy": {
            "allowlisted_scripts": [rel(path) for path in BUILD_SCRIPTS],
            "findings": policy_findings,
        },
        "environment": {
            "python": sys.version.split()[0],
            "workspace": str(ROOT),
            "wsl_distro": args.distro,
            "wsl_user": args.wsl_user,
            "kernel_source": args.kernel_source,
            "build_root": args.build_root,
            "wsl_list_exit_code": distro_rc,
            "wsl_list_raw": distro_output.strip(),
            "probe_exit_code": probe_rc,
            "probe_output": probe_output.strip(),
            "cache_probe_exit_code": cache_rc,
            "cache_probe_output": cache_output.strip(),
        },
        "build": build_info,
        "validation": ramssh_validation,
        "artifacts": {
            "items": artifacts,
            "fingerprint_sha256": artifact_fingerprint,
            "candidate_eligible_count": 0,
        },
        "checks": checks,
    }

    manifest_path = output_dir / "manifest.json"
    report_path = output_dir / "report.md"
    atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    atomic_write(report_path, markdown_report(manifest))
    manifest_hash = sha256_file(manifest_path)
    atomic_write(output_dir / "manifest.sha256", f"{manifest_hash}  manifest.json\n")

    print(
        f"OPENMITRASTAR_OFFLINE_{manifest['result']} "
        f"mode={args.mode} manifest={manifest_path} report={report_path}"
    )
    for check in checks:
        print(f"{check['status']} {check['id']}: {check['detail']}")
    return 0 if manifest["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
