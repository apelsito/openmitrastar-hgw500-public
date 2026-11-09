#!/usr/bin/env python3
"""Build F187 from F186 with Lyoko session and login surfaces."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import build_f170_lyoko_foundation_runtime_fix as engine


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-1.7-f187"
OVERLAY = FOUNDATION / "overlay"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f186-navigation-shell-from-f185/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f186-navigation-shell-from-f185-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f187-session-ui-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f187-session-ui-from-f186/build"
BASE = "openmitrastar-linux510-q3-persistent-f187-session-ui-from-f186-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontend_identity() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (OVERLAY / "etc/lyoko/frontend.env").read_text(encoding="ascii").splitlines()
        if line and "=" in line
    )


@contextlib.contextmanager
def variant_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA",
    )
    old = {name: getattr(engine, name) for name in names}
    try:
        engine.SOURCE_BUILD = SOURCE_BUILD
        engine.SOURCE_BASE = SOURCE_BASE
        engine.FOUNDATION = FOUNDATION
        engine.OVERLAY = OVERLAY
        engine.ASSETS = ASSETS
        engine.OUT = OUT
        engine.BASE = BASE
        engine.PRODUCT_VERSION = "lyoko-foundation-1.7-f187"
        engine.ASSETS_SCHEMA = "openmitrastar.f187-session-ui-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f187-session-ui-rootfs-diff/v1"
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    with variant_context():
        rc = engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    identity = frontend_identity()
    manifest.update({
        "schema": "openmitrastar.f187-session-ui/v1",
        "classification": "F187_LYOKO_SESSION_AND_LOGIN_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {"firmware": "F186", "installed_firmware": "F170"},
        "change_scope": {
            "login": "Lyoko-branded static login backed by the existing password hash and CGI session contract",
            "session_api": "authenticated metadata without tokens, client hashes or credentials",
            "logout": "explicit dashboard control using the existing session revocation endpoint",
            "identity": "login HTML and CSS included in the deterministic frontend build ID",
            "kernel_radios_packages_storage": "byte-identical to F186",
        },
        "frontend": {
            "ui_version": identity["LYOKO_UI_VERSION"],
            "build_id": identity["LYOKO_UI_BUILD_ID"],
            "source": identity["LYOKO_UI_SOURCE"],
            "asset_bytes": int(identity["LYOKO_UI_ASSET_BYTES"]),
            "html_sha256": identity["LYOKO_UI_HTML_SHA256"],
            "js_sha256": identity["LYOKO_UI_JS_SHA256"],
            "css_sha256": identity["LYOKO_UI_CSS_SHA256"],
            "login_html_sha256": identity["LYOKO_UI_LOGIN_HTML_SHA256"],
            "login_css_sha256": identity["LYOKO_UI_LOGIN_CSS_SHA256"],
        },
        "parents": {
            "f186_webformat_sha256": source["artifacts"]["webformat"]["sha256"],
            "f186_kernel_lzma_sha256": source["artifacts"]["kernel_lzma"]["sha256"],
            "f186_rootfs_sha256": source["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, real login/logout, session expiry, authenticated shell and F172 Wi-Fi campaign",
        },
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "storage_split": "not included",
        },
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
