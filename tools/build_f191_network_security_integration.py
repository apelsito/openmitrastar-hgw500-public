#!/usr/bin/env python3
"""Build F191 from the F189 network kernel and F190 security rootfs."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import build_f170_lyoko_foundation_runtime_fix as rootfs_engine
import compose_f164_squashfs_product as compose_engine


ROOT = Path(__file__).resolve().parents[1]
F189_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f189-multicast-igmp-from-f188/build"
F189_BASE = "openmitrastar-linux510-q3-persistent-f189-multicast-igmp-from-f188-LZMA-OFFLINE-NO-FLASH"
F190_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f190-ssh-identity-from-f188/build"
F190_BASE = "openmitrastar-linux510-q3-persistent-f190-ssh-identity-from-f188-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f191-network-security-integration-20260901"
FOUNDATION = ROOT / "versions/lyoko-foundation-2.0-f191"
OVERLAY = FOUNDATION / "overlay"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f191-network-security-from-f189-f190/build"
BASE = "openmitrastar-linux510-q3-persistent-f191-network-security-from-f189-f190-LZMA-OFFLINE-NO-FLASH"
EMBEDDED_HOST_KEY = "usr/share/openmitrastar/keys/device-dropbear-ed25519-host-key"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frontend_identity() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (OVERLAY / "etc/lyoko/frontend.env").read_text(encoding="ascii").splitlines()
        if line and "=" in line
    )


@contextlib.contextmanager
def rootfs_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA", "REMOVE_PATHS",
    )
    old = {name: getattr(rootfs_engine, name) for name in names}
    try:
        rootfs_engine.SOURCE_BUILD = F190_BUILD
        rootfs_engine.SOURCE_BASE = F190_BASE
        rootfs_engine.FOUNDATION = FOUNDATION
        rootfs_engine.OVERLAY = OVERLAY
        rootfs_engine.ASSETS = ASSETS
        rootfs_engine.OUT = OUT
        rootfs_engine.BASE = BASE
        rootfs_engine.PRODUCT_VERSION = "lyoko-foundation-1.9-f191"
        rootfs_engine.ASSETS_SCHEMA = "openmitrastar.f191-network-security-assets/v1"
        rootfs_engine.DIFF_SCHEMA = "openmitrastar.f191-network-security-rootfs-diff/v1"
        rootfs_engine.REMOVE_PATHS = ()
        yield
    finally:
        for name, value in old.items():
            setattr(rootfs_engine, name, value)


@contextlib.contextmanager
def compose_context():
    names = ("ASSETS", "OUT", "BASE")
    old = {name: getattr(compose_engine, name) for name in names}
    try:
        compose_engine.ASSETS = ASSETS
        compose_engine.OUT = OUT
        compose_engine.BASE = BASE
        yield
    finally:
        for name, value in old.items():
            setattr(compose_engine, name, value)


def squashfs_has_path(image: Path, path: str) -> bool:
    wsl_image = "/workspace/user-home/Desktop/MitraStar/" + image.relative_to(ROOT).as_posix()
    proc = subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", f"unsquashfs -ll '{wsl_image}' | grep -Fq '{path}'"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False,
    )
    return proc.returncode == 0


def main() -> int:
    with rootfs_context():
        rootfs_assets = rootfs_engine.prepare_assets()
    for suffix, target in {
        ".uncompressed.uImage": "kernel-squashfs.uncompressed.uImage",
        ".kernel.raw.bin": "kernel-squashfs.raw.bin",
        ".kernel.lzma": "kernel-squashfs.lzma",
        ".config": "kernel-squashfs.config",
        ".dtb": "topaz_mitrastar_squashfs.dtb",
        ".vmlinux": "kernel-squashfs.vmlinux",
    }.items():
        shutil.copy2(F189_BUILD / f"{F189_BASE}{suffix}", ASSETS / target)
    with compose_context():
        rc = compose_engine.main()
    if rc:
        return rc

    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f189 = json.loads((F189_BUILD / "manifest.json").read_text(encoding="ascii"))
    f190 = json.loads((F190_BUILD / "manifest.json").read_text(encoding="ascii"))
    identity = frontend_identity()
    rootfs = OUT / f"{BASE}.rootfs.squashfs"
    if squashfs_has_path(rootfs, EMBEDDED_HOST_KEY):
        raise SystemExit("F191 rootfs contains the forbidden embedded SSH host key")
    for required_path in ("usr/sbin/om-multicast-policy", "etc/init.d/S33-multicast-policy"):
        if not squashfs_has_path(rootfs, required_path):
            raise SystemExit(f"F191 rootfs missing {required_path}")
    config = (OUT / f"{BASE}.config").read_text(encoding="utf-8")
    for required in ("CONFIG_IP_MULTICAST=y\n", "CONFIG_BRIDGE_IGMP_SNOOPING=y\n", "CONFIG_VLAN_8021Q=y\n"):
        if required not in config:
            raise SystemExit(f"F191 kernel config missing {required.strip()}")

    manifest.update({
        "schema": "openmitrastar.f191-network-security-integration/v1",
        "classification": "F191_MULTICAST_AND_SSH_SECURITY_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "release_eligible": False,
        "source": {"kernel": "F189", "rootfs": "F190 plus release identity F191", "installed_firmware": "F170"},
        "change_scope": {
            "kernel": "exact F189 multicast/IGMP kernel with NAPI weight 128",
            "rootfs": "exact F190 security rootfs except release identity",
            "embedded_ssh_private_key": "absent",
            "multicast_policy": "compiled but forced off until traffic certification",
        },
        "parents": {
            "f189_kernel_lzma_sha256": f189["artifacts"]["kernel_lzma"]["sha256"],
            "f189_config_sha256": f189["artifacts"]["config"]["sha256"],
            "f190_rootfs_sha256": f190["artifacts"]["rootfs_squashfs"]["sha256"],
            "f190_webformat_sha256": f190["artifacts"]["webformat"]["sha256"],
        },
        "foundation_assets": rootfs_assets,
        "network_capability": f189["network_capability"],
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
        "private_key_scan": "PASS_PATH_ABSENT",
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, ephemeral SSH identity, multicast-off baseline, IGMP traffic opt-in and dual-radio regression",
        },
        "known_limitations": [
            "SSH host identity is ephemeral until lyoko_store is certified",
            "IGMP snooping remains disabled until multicast traffic certification",
        ],
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
        },
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
