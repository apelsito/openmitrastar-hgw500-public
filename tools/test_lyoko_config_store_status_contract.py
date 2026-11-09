"""Focused offline tests; no firmware builder, HTTP server, or device access.

The shell cases execute the *extracted config/store branch*, plus the original
CGI header/error functions, against temporary fake status helpers.  They do not
execute the complete CGI, authentication, real om-config-store, or its mutation
functions.  POST dispatch is stubbed and the complete source delta proves that
the real POST function and its callers are untouched.  Host grep is not the
HGW's grep: these tests verify the replacement and branch behavior, not a new
physical reproduction of the old ARC/libc regular-expression error.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

from lyoko_config_store_status_contract import (
    NEW_GUARD,
    OLD_GUARD,
    SOURCE_SHA256,
    transform_bytes,
)
from lyoko_frontend_identity import patch_api


ROOT = Path(__file__).resolve().parents[1]
F313_API = (
    ROOT
    / "versions/lyoko-foundation-6.8.1-f313-full-developer-qtn-controls"
    / "overlay/usr/libexec/openmitrastar/om-api-v1"
)
DISABLED_STATUS = {
    "schema": "openmitrastar.config-store/v1",
    "enabled": False,
    "store_ready": False,
    "active_slot": "",
    "active_valid": False,
    "format": "jffs2-ab",
    "boot_consumer": False,
    "apply_on_boot": False,
    "secrets": False,
}


def shell_path(path: Path) -> str:
    if os.name == "nt":
        value = path.resolve()
        return f"/mnt/{value.drive[0].lower()}/{value.as_posix()[3:]}"
    return str(path.resolve())


class ConfigStoreStatusContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # This existing transform is pure: it reads no rootfs and calls no WSL
        # builder.  Its output must match the independently pinned F321 hash.
        cls.before = patch_api(F313_API.read_bytes())
        if hashlib.sha256(cls.before).hexdigest() != SOURCE_SHA256:
            raise AssertionError("local source does not reconstruct exact F321 API")
        cls.after = transform_bytes(cls.before)

    def run_branch(
        self,
        payload: str,
        *,
        helper_exit: int = 0,
        missing_helper: bool = False,
        method: str = "GET",
    ) -> tuple[int, dict[str, str], str]:
        with tempfile.TemporaryDirectory(prefix="lyoko-store-contract-") as directory:
            helper = Path(directory) / "fake-config-store"
            if not missing_helper:
                helper.write_text(
                    "#!/bin/sh\n"
                    '[ "$#" = 1 ] && [ "$1" = status ] || exit 97\n'
                    f"printf '%s\\n' {shlex.quote(payload)}\n"
                    f"exit {helper_exit}\n",
                    encoding="ascii",
                    newline="\n",
                )
                helper.chmod(0o755)

            start = self.after.index(b"\nconfig/store)\n") + 1
            end = self.after.index(b"\ndiagnostics)\n", start)
            functions_start = self.after.index(b"\nheaders()\n") + 1
            functions_end = self.after.index(b"\njson_escape()\n", functions_start)
            script = (
                b"set -u\n"
                + self.after[functions_start:functions_end]
                + b"\nrun_config_store_action() { printf 'POST_DISPATCH_ONLY\\n'; }\n"
                + f"method={shlex.quote(method)}\n".encode("ascii")
                + f"config_store={shlex.quote(shell_path(helper))}\n".encode("ascii")
                + b"case config/store in\n"
                + self.after[start:end]
                + b"\nesac\n"
            )
            if os.name == "nt":
                executable = shutil.which("wsl.exe")
                if not executable:
                    self.fail("WSL is required for the focused shell-branch checks")
                command = [executable, "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-s"]
            else:
                executable = shutil.which("sh")
                if not executable:
                    self.fail("a POSIX shell is required for the focused branch checks")
                command = [executable, "-s"]
            result = subprocess.run(command, input=script, capture_output=True, timeout=15, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            self.assertEqual(result.stderr, b"")

        text = result.stdout.decode("ascii")
        if method == "POST":
            return 200, {}, text
        raw_headers, body = text.split("\r\n\r\n", 1)
        headers = dict(line.split(": ", 1) for line in raw_headers.split("\r\n"))
        status = int(headers.get("Status", "200 OK").split(" ", 1)[0])
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        return status, headers, body

    def test_exact_single_guard_delta(self) -> None:
        location = self.before.index(OLD_GUARD)
        self.assertEqual(self.before.count(OLD_GUARD), 1)
        self.assertEqual(self.after.count(NEW_GUARD), 1)
        self.assertNotIn(OLD_GUARD, self.after)
        self.assertEqual(self.after, self.before.replace(OLD_GUARD, NEW_GUARD, 1))
        self.assertEqual(self.after[:location], self.before[:location])
        self.assertEqual(self.after[location + len(NEW_GUARD):], self.before[location + len(OLD_GUARD):])
        self.assertEqual(len(self.after), len(self.before) + 1)

    def test_other_inputs_and_double_application_fail_closed(self) -> None:
        for source in (b"", self.before + b"\n", self.before.replace(b"config/store)", b"config/other)", 1), self.after):
            with self.subTest(sha256=hashlib.sha256(source).hexdigest()):
                with self.assertRaisesRegex(ValueError, "exact pinned F321"):
                    transform_bytes(source)
        with self.assertRaises(TypeError):
            transform_bytes(self.before.decode("ascii"))  # type: ignore[arg-type]

    def test_disabled_status_get_is_success_without_enabling_anything(self) -> None:
        payload = json.dumps(DISABLED_STATUS, separators=(",", ":"))
        status, _, body = self.run_branch(payload)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), DISABLED_STATUS)

    def test_disabled_status_head_uses_existing_branch_behavior(self) -> None:
        payload = json.dumps(DISABLED_STATUS, separators=(",", ":"))
        status, _, body = self.run_branch(payload, method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), DISABLED_STATUS)

    def test_wrong_or_missing_schema_is_contract_failure(self) -> None:
        for payload in (
            '{"schema":"openmitrastar.config-store/v2"}',
            '{"schema":"openmitrastar.config-store/v10"}',
            '{"schema":"other.config-store/v1"}',
            '{"enabled":false}',
            "",
        ):
            with self.subTest(payload=payload):
                status, _, body = self.run_branch(payload)
                self.assertEqual(status, 502)
                self.assertEqual(json.loads(body), {"ok": False, "error": "config-store-contract"})

    def test_missing_helper_is_unavailable(self) -> None:
        status, _, body = self.run_branch("", missing_helper=True)
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {"ok": False, "error": "config-store-unavailable"})

    def test_failing_helper_is_not_masked_by_valid_output(self) -> None:
        status, _, body = self.run_branch(json.dumps(DISABLED_STATUS, separators=(",", ":")), helper_exit=9)
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body), {"ok": False, "error": "config-store-status"})

    def test_post_is_byte_identical_and_dispatches_only_to_stub(self) -> None:
        start = self.before.index(b"\nrun_config_store_action()\n")
        end = self.before.index(b"\navailable_packages_json()\n", start)
        self.assertEqual(self.before[start:end], self.after[start:end])
        self.assertIn(b"\tPOST) run_config_store_action ;;", self.after)
        _, _, body = self.run_branch("", method="POST", missing_helper=True)
        self.assertEqual(body, "POST_DISPATCH_ONLY\n")

    def test_unsupported_method_is_still_rejected(self) -> None:
        status, _, body = self.run_branch("", method="DELETE", missing_helper=True)
        self.assertEqual(status, 405)
        self.assertEqual(json.loads(body), {"ok": False, "error": "method"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
