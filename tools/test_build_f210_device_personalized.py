from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_f210_device_personalized.py"
TEMPLATE = ROOT / "versions/lyoko-foundation-2.9-f209"


def test_template_has_no_private_key() -> None:
    assert not (TEMPLATE / "overlay/usr/share/openmitrastar/device-identity/dropbear_ed25519_host_key").exists()
    assert not (TEMPLATE / "overlay/usr/share/openmitrastar/keys/device-dropbear-ed25519-host-key").exists()


def test_personalizer_is_private_and_offline() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "PRIVATE_DEVICE_BOUND_FIRMWARE_DO_NOT_DISTRIBUTE",
        "private firmware output must be outside the workspace",
        "device identity is missing",
        "verify_embedded_key",
        "PASS_REPRODUCIBLE",
        "F210 reproducibility mismatch",
        "compose_engine.ROOTFS_WINDOW = ROOTFS_WINDOW",
        "candidate overlaps or initializes lyoko_store",
        '"flash": False',
    ):
        assert marker in text
    verifier = (ROOT / "tools/build_f196_device_personalized.py").read_text(encoding="utf-8")
    assert "embedded Dropbear fingerprint mismatch" in verifier
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in text


def test_built_private_candidate_preserves_storage_split() -> None:
    output = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f208-device-bound/manifest.json"
    if not output.is_file():
        return
    import json
    manifest = json.loads(output.read_text(encoding="ascii"))
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert manifest["storage"]["store_size"] == "0x001c0000"
    assert manifest["storage"]["store_erased_ff"] is True
    assert manifest["storage"]["candidate_ends_before_store"] is True
    assert manifest["spi_probe"]["write"] is False
