"""Offline F323 UI package tests using pinned static inputs and temporary files.

No package is published and no firmware builder, image, device, credential,
network connection, or hardware interface is used.  Hashes are deliberately
rebound in semantic rejection tests so those tests reach the relevant gate.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import package_f323_browser_compat as package


FRONTEND = "etc/lyoko/frontend.env"
NEXT_ENV = "etc/lyoko/web-next.env"
BUNDLE = "etc/lyoko/web-next.json"
DASHBOARD = "usr/share/openmitrastar/web/dashboard.html"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def identity_bytes(value: dict[str, str]) -> bytes:
    return ("\n".join(f"{key}={data}" for key, data in value.items()) + "\n").encode("ascii")


class F323PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload, cls.manifest = package.prepare_payload()
        cls.base_manifest, cls.original = package.base_payload()
        cls.verification = json.loads(package.VERIFICATION.read_text(encoding="ascii"))

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="f323-package-test-")
        self.addCleanup(temporary.cleanup)
        self.scratch = Path(temporary.name)
        self.overlay = self.scratch / "overlay"
        self.write_payload(self.payload)

    def write_payload(self, payload: dict[str, bytes]) -> None:
        for relative, data in payload.items():
            target = self.overlay / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def rebound(self, replacements: dict[str, bytes]) -> dict:
        """Rebind the outer catalogue only; inner contract checks must still run."""
        payload = {**self.payload, **replacements}
        self.write_payload(payload)
        manifest = deepcopy(self.manifest)
        for row in manifest["files"]:
            data = payload[row["path"]]
            row.update(bytes=len(data), sha256=sha256(data))
        manifest["total_bytes"] = sum(map(len, payload.values()))
        return manifest

    def rebound_bundle(self, bundle: dict) -> dict:
        return self.rebound({BUNDLE: json_bytes(bundle)})

    def rebound_active_asset(self, relative: str, data: bytes) -> dict:
        """Keep all self-reported hashes/counts coherent after asset tampering."""
        bundle = json.loads(self.payload[BUNDLE])
        row = next(row for row in bundle["assets"] if row["path"] == relative)
        row.update(bytes=len(data), sha256=sha256(data))
        bundle["asset_bytes"] = sum(row["bytes"] for row in bundle["assets"])
        replacements = {relative: data, BUNDLE: json_bytes(bundle)}
        if relative == DASHBOARD:
            identity = package.read_identity(self.payload[FRONTEND])
            identity["LYOKO_UI_DASHBOARD_HTML_SHA256"] = sha256(data)
            identity["LYOKO_UI_ASSET_BYTES"] = str(
                int(identity["LYOKO_UI_ASSET_BYTES"]) - len(self.payload[DASHBOARD]) + len(data)
            )
            replacements[FRONTEND] = identity_bytes(identity)
        return self.rebound(replacements)

    def test_payload_and_manifest_are_deterministic(self) -> None:
        with patch("subprocess.run", side_effect=AssertionError("offline package must not launch subprocesses")):
            payload, manifest = package.prepare_payload()
        self.assertEqual(payload, self.payload)
        self.assertEqual(manifest, self.manifest)
        self.assertIsNot(payload, self.payload)
        self.assertIsNot(manifest, self.manifest)
        self.assertEqual(manifest["total_bytes"], sum(map(len, payload.values())))

    def test_valid_package_returns_exact_file_catalogue(self) -> None:
        expected = package.validate_package(self.overlay, self.manifest)
        self.assertIsInstance(expected, dict)
        self.assertEqual(expected, {row["path"]: row for row in self.manifest["files"]})
        self.assertEqual(set(expected), set(self.payload))
        self.assertTrue(all(row["mode"] == "0644" for row in expected.values()))

    def test_paths_and_compiled_bytes_match_the_verified_static_inputs(self) -> None:
        expected_paths = {FRONTEND, NEXT_ENV, BUNDLE, DASHBOARD}
        for row in self.verification["build"]["assets"]:
            name = Path(row["file"]).name
            relative = "www/assets/" + ("" if name in package.BRANDS else "lyoko-next/") + name
            expected_paths.add(relative)
            self.assertEqual(self.payload[relative], (package.DIST / row["file"]).read_bytes())
            self.assertEqual(sha256(self.payload[relative]), row["sha256"])
            self.assertEqual(len(self.payload[relative]), row["bytes"])
        self.assertEqual(set(self.payload), expected_paths)
        self.assertNotIn(b"./assets/", self.payload[DASHBOARD])
        self.assertIn(b"/assets/lyoko-next/", self.payload[DASHBOARD])

    def test_styles_and_all_original_brands_are_byte_identical_to_f321(self) -> None:
        styles = {path for path in self.payload if path.endswith(".css")}
        self.assertEqual(len(styles), 1)
        self.assertEqual({Path(path).name for path in package.web.BRAND_PATHS}, package.BRANDS)
        for relative in styles | package.web.BRAND_PATHS:
            with self.subTest(path=relative):
                self.assertEqual(self.payload[relative], self.original[relative])

    def test_frontend_identity_preserves_legacy_hashes_and_updates_dashboard_total(self) -> None:
        old = package.read_identity(self.original[FRONTEND])
        actual = package.read_identity(self.payload[FRONTEND])
        allowed = {"LYOKO_UI_VERSION", "LYOKO_UI_BUILD_ID", "LYOKO_UI_SOURCE",
                   "LYOKO_UI_DASHBOARD_HTML_SHA256", "LYOKO_UI_ASSET_BYTES"}
        self.assertEqual(actual.keys(), old.keys())
        self.assertEqual({key: value for key, value in actual.items() if key not in allowed},
                         {key: value for key, value in old.items() if key not in allowed})
        self.assertEqual(actual["LYOKO_UI_VERSION"], "0.3.1-classic-compat")
        self.assertEqual(actual["LYOKO_UI_BUILD_ID"], self.manifest["build_id"])
        self.assertEqual(actual["LYOKO_UI_SOURCE"], "lyoko-classic-compat-" + self.manifest["build_id"])
        self.assertEqual(actual["LYOKO_UI_DASHBOARD_HTML_SHA256"], sha256(self.payload[DASHBOARD]))
        self.assertEqual(int(actual["LYOKO_UI_ASSET_BYTES"]),
                         int(old["LYOKO_UI_ASSET_BYTES"]) - len(self.original[DASHBOARD]) + len(self.payload[DASHBOARD]))

    def test_session_entry_and_mutation_metadata_remain_f321_values(self) -> None:
        old = package.read_identity(self.original[NEXT_ENV])
        actual = package.read_identity(self.payload[NEXT_ENV])
        self.assertEqual(actual, {**old, "LYOKO_WEB_NEXT_VERSION": "0.3.1-classic-compat",
                                 "LYOKO_WEB_NEXT_BUILD_ID": self.manifest["build_id"]})
        self.assertEqual(actual["LYOKO_WEB_NEXT_RELEASE_ELIGIBLE"], "0")
        self.assertEqual(actual["LYOKO_WEB_NEXT_AUTH"], "existing-omsession-cgi")

    def test_bundle_identity_urls_hashes_and_totals_match_active_files(self) -> None:
        bundle = json.loads(self.payload[BUNDLE])
        self.assertEqual(bundle["schema"], "lyoko.frontend.bundle/v1")
        self.assertEqual(bundle["ui_version"], self.manifest["ui_version"])
        self.assertEqual(bundle["build_id"], self.manifest["build_id"])
        self.assertEqual(bundle["entry"], "/dashboard.cgi")
        self.assertIs(bundle["legacy_assets_retained"], True)
        active = {path for path in self.payload if path.startswith(("www/", "usr/share/"))}
        self.assertEqual({row["path"] for row in bundle["assets"]}, active)
        for row in bundle["assets"]:
            path = row["path"]
            self.assertEqual(row["url"], "/dashboard.cgi" if path == DASHBOARD else "/" + path.removeprefix("www/"))
            self.assertEqual(row["bytes"], len(self.payload[path]))
            self.assertEqual(row["sha256"], sha256(self.payload[path]))
        self.assertEqual(bundle["asset_bytes"], sum(len(self.payload[path]) for path in active))

    def test_overlay_has_no_f314_retransform_or_executable_api(self) -> None:
        self.assertEqual(self.manifest["transforms"], [])
        self.assertNotIn(package.web.API_PATH, self.payload)
        self.assertTrue(self.base_manifest["transforms"], "fixture must expose the old transform")
        manifest = deepcopy(self.manifest)
        manifest["transforms"] = deepcopy(self.base_manifest["transforms"])
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, manifest)

    def test_overlay_and_manifest_cannot_grant_runtime_authority(self) -> None:
        for key in ("release_eligible", "flash_supported", "firmware_generated"):
            self.assertIs(self.manifest[key], False)
            for value in (True, 0, 1, None, "false"):
                with self.subTest(key=key, value=value):
                    manifest = deepcopy(self.manifest)
                    manifest[key] = value
                    with self.assertRaises(ValueError):
                        package.validate_package(self.overlay, manifest)
            with self.subTest(key=key, missing=True):
                manifest = deepcopy(self.manifest)
                del manifest[key]
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_safety_metadata_cannot_grant_authority(self) -> None:
        for key in ("hardware_actions", "flash", "radio_mutation", "persistent_writes_enabled"):
            for value in (True, 0, 1, None, "false"):
                with self.subTest(key=key, value=value):
                    manifest = deepcopy(self.manifest)
                    manifest["safety"][key] = value
                    with self.assertRaises(ValueError):
                        package.validate_package(self.overlay, manifest)
        manifest = deepcopy(self.manifest)
        manifest["safety"]["mtd_writes"] = True
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, manifest)

    def test_required_metadata_cannot_be_missing_or_expanded(self) -> None:
        for key in ("ui_version", "total_bytes", "source", "integration", "safety", "budgets"):
            with self.subTest(missing=key):
                manifest = deepcopy(self.manifest)
                del manifest[key]
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)
        for key in ("source", "integration", "safety", "budgets"):
            with self.subTest(expanded=key):
                manifest = deepcopy(self.manifest)
                manifest[key]["unverified_metadata"] = True
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_manifest_version_count_and_provenance_drift_are_rejected(self) -> None:
        mutations = (
            ("ui_version", "99.0.0"),
            ("total_bytes", self.manifest["total_bytes"] + 1),
            ("source", {**self.manifest["source"], "verification_sha256": "0" * 64}),
            ("source", {**self.manifest["source"], "base_f321_manifest_sha256": "0" * 64}),
            ("source", {**self.manifest["source"], "dist_index_sha256": "0" * 64}),
            ("source", {**self.manifest["source"], "dist_assets": []}),
            ("source", {**self.manifest["source"], "verified_inputs": []}),
            ("integration", {**self.manifest["integration"], "same_origin": False}),
            ("integration", {**self.manifest["integration"], "authenticated_entry": "/public.html"}),
            ("budgets", {**self.manifest["budgets"], "js_brotli": 0}),
            ("budgets", {**self.manifest["budgets"], "css_brotli": 0}),
        )
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                manifest = deepcopy(self.manifest)
                manifest[key] = value
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_invalid_build_ids_and_different_schema_are_rejected(self) -> None:
        for key, value in (("schema", "openmitrastar.lyoko-web-next-overlay/v3"),
                           *(("build_id", value) for value in (None, 16, "", "a" * 15, "a" * 17, "A" * 16, "0" * 16))):
            with self.subTest(key=key, value=value):
                manifest = deepcopy(self.manifest)
                manifest[key] = value
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_asset_corruption_and_truncation_are_rejected(self) -> None:
        relative = next(path for path in self.payload if path.endswith(".js"))
        original = self.payload[relative]
        for bad in (bytes([original[0] ^ 1]) + original[1:], original[:-1]):
            with self.subTest(size=len(bad)):
                (self.overlay / relative).write_bytes(bad)
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, self.manifest)

    def test_manifest_hash_size_mode_and_duplicate_path_drift_are_rejected(self) -> None:
        for key, value in (("sha256", "0" * 64), ("bytes", 0), ("mode", "0755")):
            with self.subTest(key=key):
                manifest = deepcopy(self.manifest)
                manifest["files"][0][key] = value
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)
        manifest = deepcopy(self.manifest)
        manifest["files"].append(deepcopy(manifest["files"][0]))
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, manifest)

    def test_unsafe_and_out_of_scope_paths_are_rejected(self) -> None:
        for path in ("../outside", "/etc/passwd", "www\\assets\\escape.js", "www/./assets/extra.js",
                     "usr/libexec/openmitrastar/om-api-v1", "etc/lyoko/autorun.env"):
            with self.subTest(path=path):
                manifest = deepcopy(self.manifest)
                manifest["files"][0]["path"] = path
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_unmanifested_file_is_rejected(self) -> None:
        (self.overlay / "www/extra.txt").write_bytes(b"unlisted")
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, self.manifest)

    def test_rebound_styles_and_brand_changes_are_rejected(self) -> None:
        paths = sorted(package.web.BRAND_PATHS | {path for path in self.payload if path.endswith(".css")})
        for path in paths:
            with self.subTest(path=path):
                manifest = self.rebound_active_asset(path, self.payload[path] + b"\n")
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_rebound_javascript_must_still_match_verified_build(self) -> None:
        relative = next(path for path in self.payload if path.endswith(".js"))
        manifest = self.rebound_active_asset(relative, self.payload[relative] + b"\n/* unverified change */\n")
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, manifest)

    def test_rebound_dashboard_cannot_add_an_external_script(self) -> None:
        data = self.payload[DASHBOARD] + b'\n<script src="https://invalid.example/injected.js"></script>\n'
        manifest = self.rebound_active_asset(DASHBOARD, data)
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, manifest)

    def test_bundle_metadata_changes_are_rejected_after_outer_hash_rebind(self) -> None:
        for key, value in (("schema", "other/v1"), ("build_id", "0" * 16), ("ui_version", "9.9.9"),
                           ("source", "other"), ("entry", "/public.html"), ("legacy_assets_retained", False)):
            with self.subTest(key=key):
                bundle = json.loads(self.payload[BUNDLE])
                bundle[key] = value
                manifest = self.rebound_bundle(bundle)
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_bundle_hash_size_and_url_drift_are_rejected_after_outer_hash_rebind(self) -> None:
        for key, value in (("sha256", "0" * 64), ("bytes", 0),
                           ("url", "https://invalid.example/script.js"), ("url", "/wrong-path.js")):
            with self.subTest(key=key, value=value):
                bundle = json.loads(self.payload[BUNDLE])
                bundle["assets"][0][key] = value
                manifest = self.rebound_bundle(bundle)
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_bundle_missing_duplicate_assets_and_total_drift_are_rejected(self) -> None:
        for mutation in ("missing", "duplicate", "total"):
            with self.subTest(mutation=mutation):
                bundle = json.loads(self.payload[BUNDLE])
                if mutation == "missing":
                    bundle["assets"].pop()
                elif mutation == "duplicate":
                    bundle["assets"].append(deepcopy(bundle["assets"][0]))
                else:
                    bundle["asset_bytes"] += 1
                manifest = self.rebound_bundle(bundle)
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_frontend_metadata_drift_is_rejected_after_outer_hash_rebind(self) -> None:
        for key, value in (("LYOKO_UI_BUILD_ID", "0" * 16), ("LYOKO_UI_VERSION", "9.9.9"),
                           ("LYOKO_UI_SOURCE", "other"), ("LYOKO_UI_APP_JS_SHA256", "0" * 64),
                           ("LYOKO_UI_DASHBOARD_HTML_SHA256", "0" * 64), ("LYOKO_UI_ASSET_BYTES", "0")):
            with self.subTest(key=key):
                identity = package.read_identity(self.payload[FRONTEND])
                identity[key] = value
                manifest = self.rebound({FRONTEND: identity_bytes(identity)})
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_session_mutation_and_release_metadata_changes_are_rejected(self) -> None:
        for key, value in (("LYOKO_WEB_NEXT_AUTH", "none"), ("LYOKO_WEB_NEXT_MUTATION_MODE", "automatic"),
                           ("LYOKO_WEB_NEXT_RELEASE_ELIGIBLE", "1"), ("LYOKO_WEB_NEXT_ENTRY", "/www/public.html"),
                           ("LYOKO_WEB_NEXT_ASSET_ROOT", "/www")):
            with self.subTest(key=key):
                identity = package.read_identity(self.payload[NEXT_ENV])
                identity[key] = value
                manifest = self.rebound({NEXT_ENV: identity_bytes(identity)})
                with self.assertRaises(ValueError):
                    package.validate_package(self.overlay, manifest)

    def test_duplicate_and_malformed_identity_lines_are_rejected(self) -> None:
        for relative in (FRONTEND, NEXT_ENV):
            for suffix in (self.payload[relative].splitlines()[0] + b"\n", b"MALFORMED\n"):
                with self.subTest(path=relative, duplicate=b"=" in suffix):
                    manifest = self.rebound({relative: self.payload[relative] + suffix})
                    with self.assertRaises(ValueError):
                        package.validate_package(self.overlay, manifest)

    def make_symlink(self, link: Path, target: Path, *, directory: bool = False) -> None:
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"real symlink creation is unavailable: {error}")

    def test_symlink_asset_is_rejected_even_with_matching_bytes(self) -> None:
        relative = next(path for path in self.payload if path.endswith(".js"))
        target = self.scratch / "linked.js"
        target.write_bytes(self.payload[relative])
        link = self.overlay / relative
        link.unlink()
        self.make_symlink(link, target)
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, self.manifest)

    def test_symlink_parent_is_rejected_even_with_matching_bytes(self) -> None:
        parent = self.overlay / "www/assets/lyoko-next"
        moved = self.scratch / "linked-assets"
        parent.rename(moved)
        self.make_symlink(parent, moved, directory=True)
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, self.manifest)

    def test_symlink_overlay_root_is_rejected_even_with_matching_bytes(self) -> None:
        moved = self.scratch / "linked-overlay"
        self.overlay.rename(moved)
        self.make_symlink(self.overlay, moved, directory=True)
        with self.assertRaises(ValueError):
            package.validate_package(self.overlay, self.manifest)

    def test_verification_record_hash_drift_is_rejected(self) -> None:
        verification = self.scratch / "verification.json"
        verification.write_bytes(package.VERIFICATION.read_bytes() + b"\n")
        with patch.object(package, "VERIFICATION", verification):
            with self.assertRaises(ValueError):
                package.prepare_payload()

    def test_base_manifest_hash_drift_is_rejected(self) -> None:
        base = self.scratch / "base"
        base.mkdir()
        (base / "manifest.json").write_bytes(b"{}\n")
        with patch.object(package, "BASE", base):
            with self.assertRaises(ValueError):
                package.prepare_payload()

    def test_compiled_input_drift_is_rejected_without_rebuilding(self) -> None:
        for mutation in ("javascript", "index", "extra-asset"):
            with self.subTest(mutation=mutation):
                dist = self.scratch / mutation
                shutil.copytree(package.DIST, dist)
                if mutation == "javascript":
                    target = next((dist / "assets").glob("*.js"))
                    target.write_bytes(target.read_bytes() + b"\n/* changed */\n")
                elif mutation == "index":
                    target = dist / "index.html"
                    target.write_bytes(target.read_bytes() + b"\n")
                else:
                    (dist / "assets/extra-1234.js").write_bytes(b"export {};\n")
                with self.assertRaises(ValueError):
                    package.prepare_payload(dist)

    def test_verified_source_drift_is_rejected(self) -> None:
        for source in self.verification["source_files"]:
            original = package.ROOT / source["path"]
            target = self.scratch / source["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original.read_bytes())
        target = self.scratch / self.verification["source_files"][0]["path"]
        target.write_bytes(target.read_bytes() + b"\n")
        with patch.object(package, "ROOT", self.scratch):
            with self.assertRaises(ValueError):
                package.prepare_payload()


if __name__ == "__main__":
    unittest.main(verbosity=2)
