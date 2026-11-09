"""Reconcile the exact F321 installation using existing, immutable evidence.

File-only: this program cannot contact the router or invoke hardware helpers.
The original promoter STOP remains unchanged. A successful reconciliation is
limited to the recorded flash, boot and independent post-boot observations;
it does not qualify a release or authorize another hardware operation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
CYCLE = ROOT / "outputs/flash-watch/f321-direct-20260907T235105Z-b42111c6"
CANDIDATE_DIR = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound"
PACKAGE = ROOT / "outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9"
REVIEW_SHA = "467dab559f828594d9d94c8146259158a10a83a107f94c4cef9bbb5095c7c174"
MANIFEST_SHA = "2b8b2f2b2e2b845c1fe660b7f89feb34da113b60ad43c6c42f312f3621dc87ff"
PACKAGE_SHA = "4c2a8b9536e28a55fc051a66f7a98df85b0417b90a3274d9f9d3c0c040a8626e"
CANDIDATE_SHA = "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18"
FULL_SLOT_SHA = "076afb4ba70b511947d1bd6f78eb5b3b62378889a4e20930a7b5c8022589cbc8"
F314_SHA = "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
IMAGE_NAME = "openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin"
VERSION = "lyoko-foundation-6.8.5-f321-classic-ui-f314-device"
KERNEL = "5.10.260-openmitrastar-radiohw"
UI_BUILD = "72dd5d1877544af9"
HOST = "192.168.1.90"
IMAGE_BYTES, SLOT_BYTES, ERASE_BYTES = 5337088, 0x7A0000, 0x5E0000
IMAGE_CRC, SLOT_CRC, F314_CRC = "bd1135df", "6ed8e483", "d6b13baa"
PROTECTED = {
    "mtd0": (0x0, 0x20000, "347cf8db"),
    "mtd1": (0x20000, 0x10000, "05624c17"),
    "mtd2": (0x30000, 0x10000, "13b7c1f7"),
    "mtd3": (0x40000, SLOT_BYTES, "f7d14d3d"),
    "mtd5": (0xF80000, 0x80000, "1165e46d"),
}
BOOT_WARNING = "pci 0000:00:00.0: BAR 0: failed to assign [io  size 0x0100]"
BOOTBASE_ERROR = re.compile(r"(?im)(data abort|machine check|unknown command|command not found|usage:|\b(?:fail(?:ed|ure)?|error)\b|ret_size=-[0-9]+)")
FATAL = re.compile(r"(?im)(Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|VFS: Unable to mount root|MuC:.*exception|MuC has halted|Machine check|Data abort)")
PLATFORM_CHECKS = frozenset((
    "ssh_pinned_identity", "transcript", "kernel", "release", "boot_ready", "rootfs_window", "store_window",
    "root_squashfs_ro", "run_tmpfs", "tmp_tmpfs", "persist_ro", "radio2_ready", "radio5_ready", "bridge_members",
    "device_identity", "web_credential", "package_verifier", "spi_probe_disabled", "multicast_initialized",
    "api_status", "api_firmware", "api_storage", "login_page", "dashboard_protected", "legacy_dashboard_removed",
    "api_protected", "no_fatal",
))
AUTH_CHECKS = frozenset((
    "login_page", "login_redirect", "session_cookie", "authenticated_dashboard_exact_bytes", "dashboard_headers",
    "authenticated_frontend_bundle", "authenticated_session_api", "logout", "session_invalid_after_logout",
    "dashboard_protected_after_logout",
))
NOT_PROVEN = [
    "repeatable cold boot or power-cycle endurance",
    "mtd3/linux_safety bootability or a new rollback rehearsal",
    "physical Wi-Fi client association, bidirectional traffic or RF soak",
    "native DFS detection, CAC, radar evacuation, NOP or DFS transmit authority",
    "on-device browser JavaScript execution or HTTPS/TLS",
    "a SHA-256 digest measured from the physical full slot",
    "full port completion or release eligibility",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


class Evidence:
    """Read each input once and bind precisely the bytes that were checked."""
    def __init__(self) -> None:
        self.files: dict[str, dict] = {}

    def data(self, path: Path, expected_sha: str | None = None) -> bytes:
        path = path.resolve(strict=True)
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        require(expected_sha is None or sha == expected_sha, "evidence hash mismatch: " + str(path))
        previous = self.files.get(str(path))
        require(previous is None or previous["sha256"] == sha, "input changed during reconciliation")
        self.files[str(path)] = {"path": str(path), "bytes": len(data), "sha256": sha}
        return data

    def text(self, path: Path, expected_sha: str | None = None) -> str:
        return self.data(path, expected_sha).decode("utf-8-sig")

    def json(self, path: Path, expected_sha: str | None = None) -> dict:
        value = json.loads(self.text(path, expected_sha))
        require(isinstance(value, dict), "JSON object required: " + str(path))
        return value


def child(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    require(bool(relative) and not path.is_absolute() and ".." not in path.parts
            and re.fullmatch(r"[A-Za-z0-9_./-]+", relative) is not None, "unsafe evidence-relative path")
    result = root.joinpath(*path.parts).resolve(strict=True)
    require(result.is_relative_to(root.resolve()), "evidence path escapes its directory")
    return result


def verify_sealed_inputs(evidence: Evidence, candidate: Path, package_dir: Path) -> tuple[dict, dict, dict]:
    manifest = evidence.json(candidate / "manifest.json", MANIFEST_SHA)
    require(manifest.get("schema") == "openmitrastar.f321-classic-ui-candidate/v1"
            and manifest.get("source", {}).get("candidate_sha256") == F314_SHA, "wrong candidate or base")
    require(all(manifest.get(key) is False for key in ("candidate_eligible", "flash_supported", "release_eligible"))
            and manifest.get("physical_validation", {}).get("authorized") is False, "sealed candidate authority flags changed")
    require(manifest.get("safety", {}).get("protected_partitions") == list(PROTECTED), "protected partition contract changed")
    data = evidence.data(candidate / IMAGE_NAME, CANDIDATE_SHA)
    require(len(data) == IMAGE_BYTES and len(data) <= ERASE_BYTES, "candidate byte size or slot-fit mismatch")
    padded = data + b"\xff" * (SLOT_BYTES - len(data))
    require(hashlib.sha256(padded).hexdigest() == FULL_SLOT_SHA
            and f"{zlib.crc32(padded) & 0xffffffff:08x}" == SLOT_CRC, "local padded-slot identity mismatch")
    require(manifest["artifacts"]["webformat"]["sha256"] == CANDIDATE_SHA
            and manifest["artifacts"]["webformat"]["bytes"] == IMAGE_BYTES
            and manifest["artifacts"]["full_slot"] == {"bytes": SLOT_BYTES, "crc32": SLOT_CRC, "sha256": FULL_SLOT_SHA},
            "manifest artifact identity mismatch")
    package = evidence.json(package_dir / "manifest.json", PACKAGE_SHA)
    require(package.get("build_id") == UI_BUILD, "wrong packaged UI build")
    files: dict[str, str] = {}
    for row in package["files"]:
        data = evidence.data(child(package_dir / "overlay", row["path"]), row["sha256"])
        require(len(data) == row["bytes"] and "/" + row["path"] not in files, "packaged UI size or duplicate path")
        files["/" + row["path"]] = row["sha256"]
    release = manifest["change_scope"]["release_identity"]
    files["/" + release["path"]] = release["sha256"]
    for row in manifest["change_scope"]["api_transform"]:
        files["/" + row["path"]] = row["after_sha256"]
    require(len(files) == 12, "unexpected installed file contract")
    bundle = evidence.json(package_dir / "overlay/etc/lyoko/web-next.json")
    require(bundle.get("build_id") == UI_BUILD, "bundle identity mismatch")
    return manifest, files, bundle


def verify_snapshot(evidence: Evidence, directory: Path) -> dict:
    review = evidence.json(directory / "executor-review.json", REVIEW_SHA)
    require(review.get("schema") == "openmitrastar.f321-executor-review/v1"
            and review.get("status") == "PASS_OFFLINE_EXECUTOR_REVIEW"
            and review.get("candidate_sha256") == CANDIDATE_SHA
            and review.get("candidate_manifest_sha256") == MANIFEST_SHA, "wrong execution-time review")
    rows = review.get("files", [])
    require(len(rows) == 20 and len({row["path"] for row in rows}) == 20, "incomplete executor snapshot")
    for row in rows:
        evidence.data(child(directory, row["path"]), row["sha256"])
    qualification = review["qualification"]
    xml = evidence.data(Path(qualification["path"]), qualification["sha256"])
    tree = ET.fromstring(xml)
    require(qualification["passed"] == 50 and len(tree.findall(".//testcase")) == 50
            and not any(tree.findall(".//" + kind) for kind in ("failure", "error", "skipped")),
            "original executor qualification is incomplete or failed")
    backend = evidence.text(directory / "tools/f321_mtd4_bootbase_flash.ps1")
    require("throw \"Bootbase failure during $Stage\"" in backend
            and "fail(?:ed|ure)?|error" in backend, "recorded parser false-positive cause not present")
    return {"review_sha256": REVIEW_SHA, "snapshot_files_verified": 20, "original_qualification_passed": 50}


def verify_uart(trace: str, backend: str) -> dict:
    """Validate exact ordered commands and their responses, not PASS labels alone."""
    cursor = 0

    def take(command: str, allow_boot: bool = False) -> str:
        nonlocal cursor
        require(cursor < len(records) and records[cursor][0] == command, "missing, reordered or unexpected UART command: " + command)
        response = records[cursor][1]
        cursor += 1
        require(allow_boot or not BOOTBASE_ERROR.search(response), "Bootbase command reported failure: " + command)
        return response

    def env() -> None:
        response = take("printenv bootcmd; printenv bootselect")
        require(re.findall(r"(?m)^bootcmd=(.*)$", response) == ["bootselect"]
                and re.findall(r"(?m)^bootselect=(.*)$", response) == ["0"], "boot environment differs from the unchanged baseline")

    def crc(memory: int, size: int, expected: str) -> None:
        response = take(f"crc32 0x{memory:08x} 0x{size:08x} 0x84000000; md.l 0x84000000 1")
        require(re.findall(r"(?m)^84000000: ([0-9a-f]{8})\s", response) == [expected], "UART CRC missing, duplicated or different")

    def read_crc(offset: int, size: int, expected: str) -> None:
        response = take(f"spi_flash read 0x{offset:08x} 0x86000000 0x{size:08x}")
        ack = f"Read: flash=0x{offset:x} mem=0x86000000 size={size} ret_size={size}"
        require(re.findall(r"(?m)^Read:.*$", response) == [ack], "incomplete or different physical read")
        crc(0x86000000, size, expected)

    # Text is normalized once so CRLF does not alter exact response matching.
    trace = trace.replace("\r\n", "\n")
    backend = backend.replace("\r\n", "\n")
    records = [(m.group(1).strip(), m.group(2)) for m in re.finditer(r"(?ms)^topaz>([^\n]+)\n(.*?)(?=^topaz>|\Z)", trace)]
    env()
    for name in ("mtd0", "mtd1", "mtd2", "mtd5"):
        read_crc(*PROTECTED[name])
    require(re.findall(r"(?m)^filesize=(.*)$", take("printenv filesize")) == ["517000"], "RAM image size mismatch")
    require("Verifying Checksum ... OK" in take("iminfo 0x83000000"), "RAM Bootbase image checksum missing")
    crc(0x83000000, IMAGE_BYTES, IMAGE_CRC)
    read_crc(*PROTECTED["mtd3"])
    read_crc(0x7E0000, SLOT_BYTES, F314_CRC)
    response = take("spi_flash erase 0x007e0000 0x005e0000")
    require(re.findall(r"(?m)^Erase:.*$", response) == [f"Erase: flash=0x7e0000 size={ERASE_BYTES}"], "exact erase acknowledgement missing")
    read_crc(0x7E0000, ERASE_BYTES, "aa86bf2e")
    response = take("spi_flash write 0x007e0000 0x83000000 0x00517000")
    require(re.findall(r"(?m)^Write:.*$", response) == [f"Write: flash=0x7e0000 mem=0x83000000 size={IMAGE_BYTES} ret_size={IMAGE_BYTES}"], "exact write acknowledgement missing")
    read_crc(0x7E0000, SLOT_BYTES, SLOT_CRC)
    response = take("cmp.b 0x83000000 0x86000000 0x00517000")
    require(re.findall(r"(?m)^Total of ([0-9]+) bytes were the same$", response) == [str(IMAGE_BYTES)], "full candidate-prefix compare not proved")
    env()
    for name in PROTECTED:
        read_crc(*PROTECTED[name])
    boot = take("bootselect", allow_boot=True)
    require(cursor == len(records), "unexpected command after boot selection")
    require("do_bootselect: spi_flash read 0x007e0000 0x83000000 0x007a0000\n"
            f"Read: flash=0x7e0000 mem=0x83000000 size={SLOT_BYTES} ret_size={SLOT_BYTES}" in boot
            and "do_bootselect: bootm 0x83000000" in boot
            and "Verifying Checksum ... OK" in boot and "Uncompressing Kernel Image ... OK" in boot
            and "Linux version " + KERNEL + " " in boot, "persistent mtd4-to-Linux boot chain incomplete")
    require(not FATAL.search(boot), "Linux boot transcript contains a fatal marker")
    bad_lines = [line for line in boot.splitlines() if BOOTBASE_ERROR.search(line)]
    require(bad_lines == [BOOT_WARNING], "boot error is not limited to the known BAR warning")
    require(backend.count("Bootbase failure during flash boot network ready") == 1
            and backend.count(BOOT_WARNING) == 1, "promoter stop is not the known Linux-parser false positive")
    for marker in (
        "MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc=f7d14d3d current_live_crc=d6b13baa",
        "OMF321_ERASED_PREFIX_CRC_PASS=1 bytes=6160384 crc=aa86bf2e",
        "PROTECTED_PARTITION_CRC_PASS=1 mtd0=347cf8db mtd1=05624c17 mtd2=13b7c1f7 mtd3=f7d14d3d mtd5=1165e46d",
        "MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc=6ed8e483 prefix=identical",
    ):
        require(backend.count(marker) == 1, "backend corroboration missing or duplicated")
    return {
        "write_target": "physical mtd4/linux_live", "offset": 0x7E0000, "erase_bytes": ERASE_BYTES,
        "candidate_bytes": IMAGE_BYTES, "candidate_prefix_compared_bytes": IMAGE_BYTES,
        "full_slot_crc32_observed": SLOT_CRC, "prewrite_full_slot_crc32_observed": F314_CRC,
        "full_slot_sha256_expected_local": FULL_SLOT_SHA, "full_slot_sha256_observed": None,
        "protected_crc32_before_and_after": {name: value[2] for name, value in PROTECTED.items()},
        "boot_environment": {"bootcmd_before_and_after": "bootselect", "bootselect_before_and_after": "0", "writes": 0},
        "mtd4_boot_chain": "PASS", "uart_network_ready": "NOT_OBSERVED_BEFORE_PARSER_ABORT",
        "hardware_digest_method": "Bootbase full-slot CRC32 plus full candidate-byte comparison",
    }


def verify_cycle(evidence: Evidence, directory: Path) -> tuple[dict, dict]:
    result = evidence.json(directory / "result.json")
    require(result.get("schema") == "openmitrastar.f321-physical-cycle/v1"
            and result.get("status") == "STOP_NO_AUTOMATIC_RETRY" and result.get("direction") == "promote"
            and result.get("candidate_sha256") == CANDIDATE_SHA and result.get("write_target") == "mtd4/linux_live"
            and result.get("helper_containment_verified") is True and result.get("radio_mutation") is False
            and result.get("spi_probe_loaded") is False and result.get("release_eligible") is False,
            "original physical-cycle result differs or was rewritten")
    plan = evidence.json(directory / "plan.json")
    require(plan.get("target_host") == HOST and plan.get("target_model") == "HGW-500BNA-QCv2 A2"
            and plan.get("write_target") == "mtd4/linux_live" and plan.get("offset") == "0x007e0000"
            and plan.get("image", {}).get("sha256") == CANDIDATE_SHA
            and plan.get("current", {}).get("sha256") == F314_SHA
            and plan.get("slot_bytes") == SLOT_BYTES and plan.get("erase_bytes") == ERASE_BYTES
            and plan.get("protected_baseline_crc32") == {name: row[2] for name, row in PROTECTED.items()}
            and plan.get("executor_review_verified") is True, "cycle plan target or identity mismatch")
    transfer = evidence.json(directory / "writer/uart-ymodem-status.json")
    require(transfer.get("status") == "PASS" and transfer.get("sha256") == CANDIDATE_SHA
            and transfer.get("bytes") == IMAGE_BYTES and transfer.get("crc32") == IMAGE_CRC
            and transfer.get("address") == "0x83000000" and transfer.get("flash_writes") == 0
            and transfer.get("environment_writes") == 0, "complete RAM transfer is not verified")
    trace = evidence.text(directory / "writer/bootbase-flash-uart.log")
    backend = evidence.text(directory / "writer/backend.log")
    physical = verify_uart(trace, backend)
    return physical, {"status": result["status"], "preserved": True,
                      "interpretation": "flash/readback completed; generic Bootbase failure regex matched Linux BAR allocation warning",
                      "automatic_retry_or_rollback_performed_by_reconciliation": False}


def timestamp(value: str, now: datetime) -> str:
    observed = datetime.fromisoformat(value)
    require(observed.tzinfo is not None and observed >= datetime(2026, 9, 7, 23, 51, 5, tzinfo=timezone.utc)
            and observed <= now + timedelta(minutes=5), "post-boot observation time is missing or outside the cycle chronology")
    return observed.astimezone(timezone.utc).isoformat()


def all_checks(checks: dict, expected: set | frozenset, label: str) -> None:
    require(isinstance(checks, dict) and set(checks) == expected and all(value is True for value in checks.values()),
            label + " check set is missing, unexpected or not all true")


def verify_postchecks(evidence: Evidence, platform_path: Path, ui_path: Path, auth_path: Path,
                      files: dict, bundle: dict, now: datetime) -> dict:
    platform = evidence.json(platform_path)
    require(platform.get("schema") == "openmitrastar.f214-device-postflash/v1" and platform.get("status") == "PASS"
            and platform.get("host") == HOST and platform.get("flash") is False, "platform gate did not pass for target")
    all_checks(platform.get("checks"), PLATFORM_CHECKS, "platform")
    stdout = evidence.text(platform_path.parent / "router.stdout.log")
    for line in ("OMF214_BEGIN", "OMF214_END", "KERNEL=" + KERNEL, "PRODUCT_VERSION=" + VERSION, "BOOT_STATE=ready",
                 "RADIO2_STATE=ENABLED", "RADIO5_STATE=ready", "RADIO5_READY=ready", "BR0_WLAN0=1", "BR0_WIFI0=1", "FATAL_COUNT=0"):
        require(stdout.splitlines().count(line) == 1, "platform transcript lacks exact post-boot identity or state: " + line)
    require(not evidence.text(platform_path.parent / "router.stderr.log").strip(), "platform SSH stderr is not empty")
    ui = evidence.json(ui_path)
    require(ui.get("schema") == "openmitrastar.f321-ui-postflash/v1"
            and ui.get("status") == "PASS_UI_FILE_API_AND_PUBLIC_HTTP" and ui.get("target_host") == HOST
            and ui.get("ui_build_id") == UI_BUILD and ui.get("flash") is False and ui.get("radio_mutation") is False,
            "UI gate did not pass for exact target/build")
    require(ui.get("ssh_checks") == {"installed_hashes": True, "frontend_api_bundle": True, "checked_files": 12},
            "UI installed-identity checks incomplete")
    expected_http = {"dashboard_protected", "public_dashboard_absent", "/api/v1/status:unauthenticated", "/api/v1/frontend:unauthenticated"}
    for row in bundle["assets"]:
        if row["url"].startswith("/assets/"):
            expected_http.add(row["url"])
            if row["url"].endswith((".js", ".css")):
                expected_http.add(row["url"] + ":mime")
    all_checks(ui.get("http_checks"), expected_http, "UI HTTP")
    stdout = evidence.text(ui_path.parent / "ssh.stdout.log").replace("\r\n", "\n")
    blocks = re.findall(r"(?ms)^OMF321_FILES_BEGIN\n(.*?)^OMF321_FILES_END$", stdout)
    require(len(blocks) == 1, "UI file transcript incomplete or duplicated")
    rows = re.findall(r"(?m)^([0-9a-f]{64})\s+(/[^\n]+)$", blocks[0])
    require(len(rows) == 12 and {path: sha for sha, path in rows} == files, "UI transcript is not the exact installed F321 files")
    blocks = re.findall(r"(?ms)^OMF321_FRONTEND_BEGIN\n(.*?)^OMF321_FRONTEND_END$", stdout)
    require(len(blocks) == 1, "UI frontend transcript incomplete or duplicated")
    payload = json.loads(blocks[0][blocks[0].find("{"):])
    require(payload.get("schema") == "lyoko.api.frontend/v1" and payload.get("asset_layout") == "split-v1"
            and payload.get("bundle") == bundle, "installed frontend API bundle mismatch")
    require(not evidence.text(ui_path.parent / "ssh.stderr.log").strip(), "UI SSH stderr is not empty")
    auth = evidence.json(auth_path)
    require(auth.get("schema") == "openmitrastar.f321-authenticated-http/v1"
            and auth.get("status") == "PASS_AUTHENTICATED_HTTP_SESSION" and auth.get("host") == HOST
            and auth.get("ui_build_id") == UI_BUILD and auth.get("transport") == "HTTP/80"
            and auth.get("flash") is False and auth.get("radio_mutation") is False
            and auth.get("password_changed") is False and auth.get("credential_logged") is False
            and auth.get("cookie_logged") is False and auth.get("session_logout_verified") is True
            and auth.get("error") is None, "authenticated HTTP evidence incomplete or unsafe")
    all_checks(auth.get("checks"), AUTH_CHECKS, "authenticated HTTP")
    return {
        "platform": {"status": platform["status"], "checks": len(PLATFORM_CHECKS), "observed_at_utc": timestamp(platform["generated_at"], now)},
        "installed_ui_and_public_http": {"status": ui["status"], "files": 12, "http_checks": len(expected_http), "observed_at_utc": timestamp(ui["generated_at_utc"], now)},
        "authenticated_http": {"status": auth["status"], "checks": len(AUTH_CHECKS), "observed_at_utc": timestamp(auth["generated_at_utc"], now)},
    }


def reconcile(cycle_dir: Path, candidate_dir: Path, package_dir: Path, platform_result: Path,
              ui_result: Path, authenticated_http_result: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    evidence = Evidence()
    _, files, bundle = verify_sealed_inputs(evidence, candidate_dir, package_dir)
    snapshot = verify_snapshot(evidence, cycle_dir / "executor-source-snapshot")
    physical, original = verify_cycle(evidence, cycle_dir)
    gates = verify_postchecks(evidence, platform_result, ui_result, authenticated_http_result, files, bundle, now)
    return {
        "schema": "openmitrastar.f321-independent-postboot-acceptance/v1",
        "status": "PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION", "generated_at_utc": now.isoformat(),
        "candidate_sha256": CANDIDATE_SHA, "product_version": VERSION, "target_host": HOST, "ui_build_id": UI_BUILD,
        "hardware_actions_performed": False, "physical_authorization_granted": False, "release_eligible": False,
        "scope": "Evidence reconciliation for this F321 cycle and the individually dated post-boot gates; no new hardware test",
        "original_promoter_result": original, "executed_source": snapshot, "physical_evidence": physical,
        "postboot_gates": gates, "not_proven": NOT_PROVEN, "evidence": list(evidence.files.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-dir", type=Path, default=CYCLE)
    parser.add_argument("--candidate-dir", type=Path, default=CANDIDATE_DIR)
    parser.add_argument("--package-dir", type=Path, default=PACKAGE)
    parser.add_argument("--platform-result", type=Path, required=True)
    parser.add_argument("--ui-result", type=Path, required=True)
    parser.add_argument("--authenticated-http-result", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    for source in (args.cycle_dir, args.candidate_dir, args.package_dir, args.platform_result.parent,
                   args.ui_result.parent, args.authenticated_http_result.parent):
        require(not output.is_relative_to(source.resolve()), "output must be outside historical input directories")
    output.mkdir(parents=True, exist_ok=False)
    try:
        result = reconcile(args.cycle_dir, args.candidate_dir, args.package_dir, args.platform_result,
                           args.ui_result, args.authenticated_http_result)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        result = {"schema": "openmitrastar.f321-independent-postboot-acceptance/v1", "status": "FAIL_EVIDENCE_RECONCILIATION",
                  "generated_at_utc": datetime.now(timezone.utc).isoformat(), "error": str(error),
                  "hardware_actions_performed": False, "release_eligible": False}
    with (output / "result.json").open("x", encoding="ascii") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "hardware_actions_performed", "release_eligible")}, indent=2))
    return 0 if result["status"] == "PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
