"""Focused offline F323 byte/layout/metadata contract tests.

Only etc/openmitrastar/release is read with unsquashfs -cat.  No extraction to
disk, builder, device, network, or store operation is performed.  Metadata
fixtures are synthetic inventories; binary fixtures use local pinned F321
bytes.  Passing verify_binary proves its byte/layout bounds, not a Bootbase
checksum, valid recompressed SquashFS, physical boot, or release acceptance.
"""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import f323_browser_compat_contract as contract
from lyoko_config_store_status_contract import NEW_GUARD, OLD_GUARD, SOURCE_SHA256
from lyoko_frontend_identity import patch_api


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound"
F321_BASE = "openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH"
F313_API = ROOT / "versions/lyoko-foundation-6.8.1-f313-full-developer-qtn-controls/overlay/usr/libexec/openmitrastar/om-api-v1"
BUILD_ID = "0123456789abcdef"


@lru_cache(maxsize=1)
def source_binary() -> tuple[bytes, bytes]:
    candidate = (PRIVATE / (F321_BASE + ".webformat.bin")).read_bytes()
    rootfs = (PRIVATE / (F321_BASE + ".rootfs.squashfs")).read_bytes()
    contract.pinned(candidate, contract.SOURCE_CANDIDATE, "test fixture F321 candidate")
    contract.pinned(rootfs, contract.SOURCE_ROOTFS, "test fixture F321 rootfs")
    return candidate, rootfs


@lru_cache(maxsize=1)
def source_release() -> bytes:
    source_binary()  # Do not inspect an unpinned local rootfs.
    rootfs = PRIVATE / (F321_BASE + ".rootfs.squashfs")
    if os.name == "nt":
        executable = shutil.which("wsl.exe")
        if not executable:
            raise RuntimeError("WSL is required for the one read-only release fixture")
        path = rootfs.resolve()
        source_path = f"/mnt/{path.drive[0].lower()}/{path.as_posix()[3:]}"
        command = [executable, "-d", "podman-mem9-tidb", "-u", "root", "-e", "unsquashfs", "-cat", source_path, contract.RELEASE_PATH]
    else:
        executable = shutil.which("unsquashfs")
        if not executable:
            raise RuntimeError("unsquashfs is required for the read-only release fixture")
        command = [executable, "-cat", str(rootfs), contract.RELEASE_PATH]
    result = subprocess.run(command, capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise RuntimeError("read-only F321 release fixture failed: " + result.stderr.decode("utf-8", errors="replace"))
    contract.pinned(result.stdout, contract.SOURCE_RELEASE, "test fixture F321 release")
    return result.stdout


def file_metadata(content: bytes, mode: int = 0o644) -> dict:
    return {"type": "file", "bytes": len(content), "sha256": contract.digest(content), "mode": mode, "uid": 0, "gid": 0}


def delta_fixture() -> tuple[dict, dict, dict, set[str]]:
    ui_path = "www/assets/lyoko-next/main-compat.js"
    directories = (".", "bin", "etc", "etc/openmitrastar", "usr", "usr/bin", "usr/sbin", "usr/libexec", "usr/libexec/openmitrastar", "www", "www/assets", "www/assets/lyoko-next")
    before = {path: {"type": "dir", "mode": 0o755, "uid": 0, "gid": 0} for path in directories}
    before.update({
        ui_path: file_metadata(b"old ui"),
        contract.API_PATH: file_metadata(b"old api", 0o755),
        contract.RELEASE_PATH: file_metadata(b"old release"),
        "usr/sbin/om-radio5-start": file_metadata(b"unchanged radio", 0o755),
        "usr/bin/grep": {"type": "symlink", "target": "../../bin/tool-a", "mode": 0o777, "uid": 0, "gid": 0},
        "bin/tool-a": {**file_metadata(b"unchanged tool", 0o755), "hardlink_group": "bin/tool-a"},
        "bin/tool-b": {**file_metadata(b"unchanged tool", 0o755), "hardlink_group": "bin/tool-a"},
    })
    changed = {
        ui_path: file_metadata(b"new ui"),
        contract.API_PATH: {**file_metadata(b"new api", 0o755), "sha256": contract.API_AFTER},
        contract.RELEASE_PATH: file_metadata(b"new release"),
    }
    after = deepcopy(before)
    after.update(changed)
    expected = {path: {"path": path, "bytes": row["bytes"], "sha256": row["sha256"], "mode": f"{row['mode']:04o}"} for path, row in changed.items()}
    return before, after, expected, {ui_path}


class ReleaseAndApiTests(unittest.TestCase):
    def test_release_changes_exactly_three_fields(self) -> None:
        source = source_release()
        output = contract.release_bytes(source, BUILD_ID)
        before, after = source.splitlines(keepends=True), output.splitlines(keepends=True)
        self.assertEqual(len(before), len(after))
        expected = {
            b"OPENMITRASTAR_PRODUCT_VERSION": contract.PRODUCT_VERSION.encode("ascii"),
            b"OPENMITRASTAR_UI_VERSION": contract.UI_VERSION.encode("ascii"),
            b"OPENMITRASTAR_BUILD_ID": BUILD_ID.encode("ascii"),
        }
        changed = set()
        for old, new in zip(before, after):
            key = old.split(b"=", 1)[0]
            if key in expected:
                self.assertEqual(new, key + b"=" + expected[key] + b"\n")
                self.assertNotEqual(old, new)
                changed.add(key)
            else:
                self.assertEqual(old, new)
        self.assertEqual(changed, set(expected))

    def test_release_rejects_drift_and_invalid_build_ids(self) -> None:
        source = source_release()
        for invalid in (b"", source + b"\n", source.replace(b"OPENMITRASTAR_BUILD_ID=", b"OTHER_BUILD_ID=", 1)):
            with self.subTest(source=contract.digest(invalid)):
                with self.assertRaisesRegex(ValueError, "source drift"):
                    contract.release_bytes(invalid, BUILD_ID)
        for build_id in ("", "0" * 15, "0" * 17, "A" * 16, "g" * 16, BUILD_ID + "\n", "../" + "a" * 13):
            with self.subTest(build_id=build_id):
                with self.assertRaisesRegex(ValueError, "invalid F323 build"):
                    contract.release_bytes(source, build_id)

    def test_api_is_exact_guard_only_and_does_not_reapply_frontend(self) -> None:
        source = patch_api(F313_API.read_bytes())
        self.assertEqual(contract.digest(source), SOURCE_SHA256)
        output = contract.api_bytes(source)
        self.assertEqual(contract.digest(output), contract.API_AFTER)
        self.assertEqual(output, source.replace(OLD_GUARD, NEW_GUARD, 1))
        self.assertEqual(len(output), len(source) + 1)
        start = source.index(b"\nfrontend)\n")
        end = source.index(b"\n\t;;", start)
        output_start = output.index(b"\nfrontend)\n")
        output_end = output.index(b"\n\t;;", output_start)
        self.assertEqual(output[output_start:output_end], source[start:end])
        self.assertEqual(output.count(b'"asset_layout":"split-v1"'), 1)
        for invalid in (F313_API.read_bytes(), source + b"\n", output):
            with self.subTest(source=contract.digest(invalid)):
                with self.assertRaisesRegex(ValueError, "exact pinned F321"):
                    contract.api_bytes(invalid)


class DeltaTests(unittest.TestCase):
    def test_exact_ui_api_release_delta_passes(self) -> None:
        before, after, expected, ui_paths = delta_fixture()
        checks = contract.verify_delta(before, after, expected, ui_paths)
        self.assertEqual(set(checks["changed_files"]), set(expected))
        self.assertEqual(checks["new_directories"], [])

    def test_rejects_extra_change_added_file_and_file_loss(self) -> None:
        for mutation in ("changed", "added", "lost-protected", "lost-ui"):
            with self.subTest(mutation=mutation):
                before, after, expected, ui_paths = delta_fixture()
                if mutation == "changed":
                    after["usr/sbin/om-radio5-start"]["sha256"] = "0" * 64
                elif mutation == "added":
                    after["usr/sbin/unlisted-helper"] = file_metadata(b"extra")
                elif mutation == "lost-protected":
                    del after["usr/sbin/om-radio5-start"]
                else:
                    del after[next(iter(ui_paths))]
                with self.assertRaises(ValueError):
                    contract.verify_delta(before, after, expected, ui_paths)

    def test_rejects_outside_ui_mode_owner_symlink_and_hardlink_drift(self) -> None:
        for mutation in ("mode", "directory-mode", "owner", "symlink", "hardlink-lost", "hardlink-retargeted"):
            with self.subTest(mutation=mutation):
                before, after, expected, ui_paths = delta_fixture()
                if mutation == "mode":
                    after["usr/sbin/om-radio5-start"]["mode"] = 0o777
                elif mutation == "directory-mode":
                    after["usr/sbin"]["mode"] = 0o777
                elif mutation == "owner":
                    after["usr/sbin/om-radio5-start"]["uid"] = 1000
                elif mutation == "symlink":
                    after["usr/bin/grep"]["target"] = "../../tmp/other"
                elif mutation == "hardlink-lost":
                    del after["bin/tool-b"]["hardlink_group"]
                else:
                    after["bin/tool-b"]["hardlink_group"] = "bin/tool-b"
                with self.assertRaises(ValueError):
                    contract.verify_delta(before, after, expected, ui_paths)

    def test_rejects_expanded_expected_set_and_wrong_api_hash_or_mode(self) -> None:
        for mutation in ("extra-expected", "missing-expected", "api-hash", "api-mode", "actual-api-mode"):
            with self.subTest(mutation=mutation):
                before, after, expected, ui_paths = delta_fixture()
                if mutation == "extra-expected":
                    expected["usr/sbin/om-radio5-start"] = {"path": "usr/sbin/om-radio5-start", "bytes": 0, "sha256": "0" * 64, "mode": "0755"}
                elif mutation == "missing-expected":
                    del expected[contract.RELEASE_PATH]
                elif mutation == "api-hash":
                    expected[contract.API_PATH]["sha256"] = "0" * 64
                elif mutation == "api-mode":
                    expected[contract.API_PATH]["mode"] = "0777"
                else:
                    after[contract.API_PATH]["mode"] = 0o777
                with self.assertRaises(ValueError):
                    contract.verify_delta(before, after, expected, ui_paths)


class BinaryBoundsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source, cls.rootfs = source_binary()

    def test_exact_baseline_passes_layout_check_only(self) -> None:
        contract.verify_binary(self.source, self.rootfs, self.source, self.rootfs)

    def test_rejects_source_candidate_or_source_rootfs_drift(self) -> None:
        with self.assertRaisesRegex(ValueError, "source drift: F321 candidate"):
            contract.verify_binary(self.source + b"\x00", self.rootfs, self.source, self.rootfs)
        with self.assertRaisesRegex(ValueError, "source drift: F321 rootfs"):
            contract.verify_binary(self.source, self.rootfs + b"\x00", self.source, self.rootfs)

    def test_rejects_each_protected_header_byte(self) -> None:
        fields = {
            "magic": range(0, 4),
            "load": range(16, 20),
            "entry": range(20, 24),
            "os": range(28, 29),
            "architecture": range(29, 30),
            "type": range(30, 31),
            "compression": range(31, 32),
            "name": range(32, 64),
        }
        for field, offsets in fields.items():
            for offset in offsets:
                with self.subTest(field=field, offset=offset):
                    candidate = bytearray(self.source)
                    candidate[offset] ^= 1
                    with self.assertRaisesRegex(ValueError, "kernel load/entry or image type metadata"):
                        contract.verify_binary(self.source, self.rootfs, bytes(candidate), self.rootfs)

    def test_rejects_kernel_and_header_padding_changes(self) -> None:
        for offset in (64, 4096, contract.ROOTFS_OFFSET - 1):
            with self.subTest(offset=offset):
                candidate = bytearray(self.source)
                candidate[offset] ^= 1
                with self.assertRaisesRegex(ValueError, "header padding or kernel"):
                    contract.verify_binary(self.source, self.rootfs, bytes(candidate), self.rootfs)

    def test_rejects_rootfs_magic_mismatch_truncation_and_trailing_bytes(self) -> None:
        bad_magic = b"xxxx" + self.rootfs[4:]
        candidates = (
            (self.source, bad_magic),
            (self.source[:contract.ROOTFS_OFFSET] + bad_magic, bad_magic),
            (self.source[:-1], self.rootfs),
            (self.source + b"\xff", self.rootfs),
            (self.source[:contract.ROOTFS_OFFSET], b""),
        )
        for candidate, rootfs in candidates:
            with self.subTest(candidate_bytes=len(candidate), rootfs_bytes=len(rootfs)):
                with self.assertRaisesRegex(ValueError, "rootfs offset or sidecar"):
                    contract.verify_binary(self.source, self.rootfs, candidate, rootfs)

    def test_store_boundary_exact_fit_and_one_byte_overflow(self) -> None:
        # Synthetic magic/length fixture, not a claim of a mountable SquashFS.
        rootfs = b"hsqs" + b"\x00" * (contract.ROOTFS_WINDOW - 4)
        candidate = self.source[:contract.ROOTFS_OFFSET] + rootfs
        self.assertEqual(len(candidate), contract.STORE_OFFSET)
        contract.verify_binary(self.source, self.rootfs, candidate, rootfs)
        with self.assertRaisesRegex(ValueError, "rootfs/store boundary"):
            contract.verify_binary(self.source, self.rootfs, candidate + b"\x00", rootfs + b"\x00")


if __name__ == "__main__":
    unittest.main(verbosity=2)
